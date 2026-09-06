import {
  Anchor,
  Badge,
  Box,
  Button,
  Card,
  Center,
  Group,
  Progress,
  ScrollArea,
  SimpleGrid,
  Skeleton,
  Stack,
  Table,
  Text,
  ThemeIcon,
  Title,
  Alert,
} from "@mantine/core";
import {
  IconAlertTriangle,
  IconArrowLeftRight,
  IconCircleCheck,
  IconExternalLink,
  IconRefresh,
  IconUrgent,
  IconDownload,
  IconPlus,
} from "@tabler/icons-react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import dayjs from "dayjs";
import relativeTime from "dayjs/plugin/relativeTime";
import { Link, useNavigate } from "react-router-dom";
import {
  fetchDashboard, fetchWards, fetchMedAdmins, updateMedAdminStatus,
  fetchAppointments, fetchLabWorklist, fetchReferrals, fetchHandovers,
  fetchShifts, fetchAlerts, acknowledgeHandover,
} from "@/api/endpoints";
import { useAuth } from "@/auth/AuthProvider";
import type {
  EncounterSummary, Role, ChartConfig, MedicationAdministration, LabResult, AuditLogEntry, Referral,
} from "@/types";
import { ChartPanel } from "./ChartPanel";
import { StatCard } from "./StatCard";
import { useState } from "react";
import { notifications } from "@mantine/notifications";

dayjs.extend(relativeTime);

const ROLE_TITLES: Record<Role, string> = {
  super_admin:    "System Administration",
  hospital_admin: "Hospital Overview",
  doctor:         "Clinical Dashboard",
  nurse:          "Nursing Dashboard",
  lab_technician: "Laboratory Dashboard",
  receptionist:   "Reception Dashboard",
};

const EMPTY_CHART: ChartConfig = {
  type: "bar",
  labels: [],
  datasets: [{ label: "Count", data: [] }],
};

export function DashboardPage() {
  const { user } = useAuth();
  const role = user?.role;
  const navigate = useNavigate();
  const [alertDismissed, setAlertDismissed] = useState(false);
  const [criticalNotified, setCriticalNotified] = useState(false);

  const queryClient = useQueryClient();

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["dashboard"],
    queryFn:  () => fetchDashboard().then((r) => r.data),
    staleTime: 2 * 60 * 1000,
  });

  const { data: wardsData } = useQuery({
    queryKey: ["wards-list"],
    queryFn: () => fetchWards().then((r) => r.data),
    enabled: role === "hospital_admin" || role === "nurse",
  });

  const { data: medAdmins, isLoading: loadingMeds } = useQuery({
    queryKey: ["mar-med-admins"],
    queryFn: () => fetchMedAdmins().then((r) => r.data),
    enabled: role === "nurse",
    refetchInterval: 15_000,
  });

  const { data: todayAppointments } = useQuery({
    queryKey: ["appointments-today"],
    queryFn: () => fetchAppointments({ date: dayjs().format("YYYY-MM-DD") }).then((r) => r.data),
    enabled: role === "doctor",
  });

  const { data: labWorklist } = useQuery({
    queryKey: ["lab-worklist-dash"],
    queryFn: () => fetchLabWorklist().then((r) => r.data),
    enabled: role === "doctor" || role === "lab_technician",
    refetchInterval: 30_000,
  });

  const { data: referralsData } = useQuery({
    queryKey: ["referrals-dash"],
    queryFn: () => fetchReferrals().then((r) => r.data.results ?? []),
    enabled: role === "doctor",
  });

  const { data: handoversData } = useQuery({
    queryKey: ["handovers-dash"],
    queryFn: () => fetchHandovers().then((r) => r.data),
    enabled: role === "nurse",
  });

  const { data: activeShiftsData } = useQuery({
    queryKey: ["shifts-admin-dash"],
    queryFn: () => fetchShifts().then((r) => r.data),
    enabled: role === "hospital_admin",
  });

  const { data: alertsFeed } = useQuery({
    queryKey: ["alerts-feed"],
    queryFn: () => fetchAlerts().then((r) => r.data),
    enabled: role === "lab_technician" || role === "hospital_admin",
    refetchInterval: 60_000,
  });

  const medMutation = useMutation({
    mutationFn: ({ id, status }: { id: number; status: string }) =>
      updateMedAdminStatus(id, status),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["mar-med-admins"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
    onError: () => {
      notifications.show({ color: "red", message: "Failed to update medication." });
    },
  });

  const handoverAckMutation = useMutation({
    mutationFn: (id: number) => acknowledgeHandover(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["handovers-dash"] });
      notifications.show({
        title: "Handover Acknowledged",
        message: "Acknowledgement recorded successfully.",
        color: "green",
      });
    },
    onError: () => {
      notifications.show({ color: "red", message: "Failed to record acknowledgement." });
    },
  });

  if (isLoading) return <DashboardSkeleton />;

  if (error) {
    return (
      <Center h={400}>
        <Stack align="center">
          <Text c="red">Failed to load dashboard. Please try again.</Text>
          <Button leftSection={<IconRefresh size={16} />} onClick={() => refetch()} variant="light">
            Retry
          </Button>
        </Stack>
      </Center>
    );
  }

  function handleExportPDF() {
    notifications.show({
      title: "Print",
      message: "Opening print dialog — use your browser's 'Save as PDF' option to export.",
      color: "blue",
    });
    window.print();
  }

  // ── BRANCH ON ROLE FOR CUSTOM WORKFLOWS ────────────────────────────────────

  if (role === "hospital_admin") {
    const totalBeds = wardsData?.reduce((s, w) => s + w.capacity, 0) || 0;
    const occupiedBeds = wardsData?.reduce((s, w) => s + w.occupied_count, 0) || 0;
    const occupancyPct = totalBeds > 0 ? Math.round((occupiedBeds / totalBeds) * 100) : 0;

    const stats = [
      { label: "Hospital patients",   value: String(data?.stats[0]?.value ?? 0), color: "blue",  delta: data?.stats[0]?.delta || "—", link: "/patients" },
      { label: "Hospital encounters", value: String(data?.stats[1]?.value ?? 0), color: "green", delta: data?.stats[1]?.delta || "—", link: "/patients" },
      { label: "Active staff",        value: String(data?.stats[2]?.value ?? 0), color: "amber", delta: data?.stats[2]?.delta || "—", link: "/staff" },
      { label: "Encounters today",    value: String(data?.stats[3]?.value ?? 0), color: "red",   delta: data?.stats[3]?.delta || "—", link: "/patients" },
    ];

    const encounterTrendChart: ChartConfig = data?.charts?.enc_trend || EMPTY_CHART;
    const encounterTypesChart: ChartConfig = data?.charts?.enc_type || data?.charts?.encounter_types || EMPTY_CHART;

    const activeShifts = activeShiftsData?.filter((s) => s.is_active) ?? [];
    const activeShiftCount = activeShifts.length;
    const topAlert = alertsFeed?.results?.[0] ?? null;

    return (
      <Stack gap="lg">
        {/* Critical alert banner — from real alerts API */}
        {topAlert && !alertDismissed && (
          <Alert
            icon={<IconAlertTriangle size={18} />}
            color="red"
            title="Critical Alert"
            withCloseButton
            onClose={() => setAlertDismissed(true)}
            styles={{ root: { backgroundColor: "var(--bg-red)", borderColor: "var(--accent-red)", color: "var(--accent-red)" } }}
          >
            <Group justify="space-between" align="center" wrap="nowrap" w="100%">
              <Text size="sm">
                {topAlert.label}
                {topAlert.patient_name ? ` — ${topAlert.patient_name}` : ""}
                {(alertsFeed?.count ?? 0) > 1 ? ` (+${(alertsFeed?.count ?? 1) - 1} more)` : ""}
              </Text>
              <Button size="xs" color="red" component={Link} to="/alerts">View all</Button>
            </Group>
          </Alert>
        )}

        {/* Header */}
        <Group justify="space-between" align="flex-start">
            <Box>
              <Title order={2} style={{ fontFamily: "'Bricolage Grotesque', sans-serif", fontWeight: 700, color: "var(--ink)", fontSize: "1.5rem" }}>Hospital Overview</Title>
              <Text c="var(--muted)" size="xs">
                {user?.hospital?.name || "Central EMR"} · {dayjs().format("dddd, D MMM YYYY")}
              </Text>
            </Box>
          <Group gap="xs">
            <Button variant="subtle" size="sm" onClick={handleExportPDF} leftSection={<IconDownload size={14} />} color="gray">
              Print / Save PDF
            </Button>
            <Button variant="subtle" size="sm" onClick={() => refetch()} leftSection={<IconRefresh size={14} />} color="gray">
              Refresh
            </Button>
          </Group>
        </Group>

        {/* Admin Stats Cards */}
        <SimpleGrid cols={{ base: 2, sm: 4 }} spacing="md">
          {stats.map((stat, i) => (
            <StatCard key={i} stat={stat} />
          ))}
        </SimpleGrid>

        {/* Second Row Widgets */}
        <SimpleGrid cols={{ base: 1, md: 2 }} spacing="md">
          {/* Bed Occupancy Progress Widget */}
          <Card withBorder radius="14px" p="md" bg="var(--card)" style={{ borderColor: "var(--line)" }}>
            <Text className="cardTitle" mb="xs">
              Bed Occupancy
            </Text>
            <Progress
              value={occupancyPct}
              color="var(--ok)"
              styles={{
                root: { backgroundColor: "var(--line)" }
              }}
              size="lg"
              radius="xl"
              mb="md"
            />
            <Group justify="space-between">
              <Text size="xs" c="var(--muted)" style={{ fontFamily: "'IBM Plex Mono', monospace" }}>{occupiedBeds} / {totalBeds} beds occupied</Text>
              <Text size="xs" fw={700} style={{ fontFamily: "'IBM Plex Mono', monospace" }}>{occupancyPct.toFixed(0)}%</Text>
            </Group>
          </Card>

          {/* Staff on Shift Widget */}
          <Card withBorder radius="14px" p="md" bg="var(--card)" style={{ borderColor: "var(--line)" }}>
            <Text className="cardTitle" mb="xs">
              Active Shifts
            </Text>
            <Title order={3} style={{ fontFamily: "'Bricolage Grotesque', sans-serif", fontWeight: 700, fontSize: "1.25rem", color: "var(--ink)", marginBottom: "0.5rem" }}>
              {activeShifts.length} staff online
            </Title>
            {activeShiftCount > 0 ? (
              <Stack gap={4} mb="md">
                {activeShifts.slice(0, 5).map((s) => (
                  <Text key={s.id} size="sm" c="dimmed">
                    {s.user_name}{s.ward_name ? ` · ${s.ward_name}` : ""}
                  </Text>
                ))}
                {activeShiftCount > 5 && (
                  <Text size="xs" c="dimmed">+{activeShiftCount - 5} more</Text>
                )}
              </Stack>
            ) : (
              <Text size="sm" c="dimmed" mb="md">No active shifts right now.</Text>
            )}
            <Button component={Link} to="/admin/shift-management" variant="subtle" size="xs" mt="auto">
              View shift schedule →
            </Button>
          </Card>
        </SimpleGrid>

        {/* Charts */}
        <SimpleGrid cols={{ base: 1, md: 2 }} spacing="md">
          <ChartPanel title="Encounter trend" chart={encounterTrendChart} />
          <ChartPanel title="Encounter types" chart={encounterTypesChart} />
        </SimpleGrid>

        {/* Recent encounters */}
        {data?.recent_encounters && data.recent_encounters.length > 0 && (
          <RecentEncountersTable encounters={data.recent_encounters} />
        )}
      </Stack>
    );
  }

  if (role === "doctor") {
    const stats = [
      { label: "My encounters",   value: String(data?.stats[0]?.value ?? 0), color: "blue",  delta: data?.stats[0]?.delta || "All time",    link: "/worklist" },
      { label: "Today",           value: String(data?.stats[1]?.value ?? 0), color: "green", delta: data?.stats[1]?.delta || "—",            link: "/worklist" },
      { label: "Patients seen",   value: String(data?.stats[2]?.value ?? 0), color: "amber", delta: data?.stats[2]?.delta || "This week",    link: "/patients" },
      { label: "Critical alerts", value: String(data?.stats[3]?.value ?? 0), color: "red",   delta: data?.stats[3]?.delta || "Needs review", link: "/alerts" },
    ];

    const waitingCount = todayAppointments?.filter(
      (a) => a.status === "scheduled" || a.status === "checked_in"
    ).length ?? 0;

    const resultedLabOrders = labWorklist?.filter((l) => l.status === "resulted") ?? [];
    const pendingReferrals = referralsData?.filter(
      (r: Referral) => r.status === "sent" || r.status === "draft"
    ).slice(0, 3) ?? [];

    return (
      <Stack gap="lg">
        {/* Header */}
        <Group justify="space-between" align="center">
          <Box>
            <Title order={2} style={{ fontSize: 20, fontWeight: 500 }}>Clinical Dashboard</Title>
            <Text c="dimmed" size="xs">
              Good {greeting()}, Dr. {user?.first_name || user?.username}
              {waitingCount > 0 ? ` · ${waitingCount} patient${waitingCount !== 1 ? "s" : ""} waiting` : ""}
            </Text>
          </Box>
          <Group gap="xs">
            <Button component={Link} to="/patients" variant="default" size="sm" leftSection={<IconExternalLink size={14} />}>
              Search patients
            </Button>
            <Button component={Link} to="/patients/new" variant="filled" size="sm" leftSection={<IconPlus size={14} />}>
              New encounter
            </Button>
          </Group>
        </Group>

        {/* Doctor Stats Cards */}
        <SimpleGrid cols={{ base: 2, sm: 4 }} spacing="md">
          {stats.map((stat, i) => (
            <StatCard key={i} stat={stat} />
          ))}
        </SimpleGrid>

        {/* Today's Worklist */}
        <Card withBorder radius="14px" p="md">
          <Group justify="space-between" mb="md">
            <Text className="cardTitle">Today's worklist</Text>
            <Button size="xs" variant="outline" leftSection={<IconPlus size={12} />} onClick={() => navigate("/patients/new")}>
              Add walk-in
            </Button>
          </Group>
          <ScrollArea>
            <Table striped highlightOnHover>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>#</Table.Th>
                  <Table.Th>Patient</Table.Th>
                  <Table.Th>NHID</Table.Th>
                  <Table.Th>Reason</Table.Th>
                  <Table.Th>Scheduled</Table.Th>
                  <Table.Th>Status</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {todayAppointments?.length === 0 ? (
                  <Table.Tr>
                    <Table.Td colSpan={6}>
                      <Text ta="center" size="sm" c="var(--muted)" py="md">No appointments scheduled for today. Add a walk-in to get started.</Text>
                    </Table.Td>
                  </Table.Tr>
                ) : (
                  todayAppointments?.map((apt, index) => {
                    let statusColor = "gray";
                    if (apt.status === "checked_in") statusColor = "clinical";
                    else if (apt.status === "scheduled") statusColor = "medsync";
                    else if (apt.status === "in_progress") statusColor = "warn";
                    else if (apt.status === "no_show") statusColor = "danger";

                    return (
                      <Table.Tr
                        key={apt.id}
                        onClick={() => navigate(`/patients/${apt.patient_nhid}`)}
                        style={{ cursor: "pointer" }}
                      >
                        <Table.Td>{index + 1}</Table.Td>
                        <Table.Td fw={500}>{apt.patient_name}</Table.Td>
                        <Table.Td ff="monospace">{apt.patient_nhid}</Table.Td>
                        <Table.Td>{apt.reason || apt.appointment_type_display}</Table.Td>
                        <Table.Td>{dayjs(apt.scheduled_for).format("HH:mm")}</Table.Td>
                        <Table.Td>
                          <Badge color={statusColor} variant="light" size="sm">{apt.status_display}</Badge>
                        </Table.Td>
                      </Table.Tr>
                    );
                  })
                )}
              </Table.Tbody>
            </Table>
          </ScrollArea>
        </Card>

        {/* Small widgets below worklist */}
        <SimpleGrid cols={{ base: 1, md: 2 }} spacing="md">
          {/* Resulted Lab Orders */}
          <Card withBorder radius="14px" p="md">
            <Group justify="space-between" mb="xs">
              <Text className="cardTitle">Resulted lab orders</Text>
              <Anchor component={Link} to="/lab/orders" size="xs">View all →</Anchor>
            </Group>
            <Stack gap="xs" mt="sm">
              {resultedLabOrders.length === 0 ? (
                <Text size="sm" c="var(--muted)">No resulted lab orders. Pending results will appear once inputted.</Text>
              ) : (
                resultedLabOrders.slice(0, 3).map((l) => (
                  <Group key={l.id} justify="space-between">
                    <Box>
                      <Text size="sm" fw={600}>{l.patient_nhid}</Text>
                      <Text size="xs" c="dimmed">
                        {l.test_name} ·{" "}
                        <span style={{ color: l.priority === "stat" ? "var(--accent-red)" : undefined, fontWeight: l.priority === "stat" ? 600 : undefined }}>
                          {l.priority_display}
                        </span>
                      </Text>
                    </Box>
                    <Button size="xs" variant="light" color={l.priority === "stat" ? "red" : "gray"} component={Link} to={`/patients/${l.patient_nhid}`}>
                      Review
                    </Button>
                  </Group>
                ))
              )}
            </Stack>
          </Card>

          {/* Active Referrals */}
          <Card withBorder radius="14px" p="md">
            <Group justify="space-between" mb="xs">
              <Text className="cardTitle">Active referrals</Text>
              <Anchor component={Link} to="/referrals" size="xs">View all →</Anchor>
            </Group>
            <Stack gap="xs" mt="sm">
              {pendingReferrals.length === 0 ? (
                <Text size="sm" c="var(--muted)">No active referrals. Sent referrals will appear here.</Text>
              ) : (
                pendingReferrals.map((r: Referral) => (
                  <Box key={r.id}>
                    <Text size="sm" fw={600}>{r.patient_name} → {r.to_hospital_name}</Text>
                    <Text size="xs" c="dimmed">{r.status_display} · {dayjs(r.created_at).fromNow()}</Text>
                  </Box>
                ))
              )}
            </Stack>
          </Card>
        </SimpleGrid>
      </Stack>
    );
  }

  if (role === "nurse") {
    // 🩺 NURSING DASHBOARD
    const stats = (data?.stats && data.stats.length > 0) ? data.stats.map((s) => ({
      label: s.label,
      value: String(s.value),
      // Normalize backend colour names ("danger", "primary", ...) to CSS/Mantine tokens
      color:
        s.color === "danger"  ? "red"    :
        s.color === "primary" ? "blue"   :
        s.color === "success" ? "green"  :
        s.color === "warning" ? "orange" : s.color,
      link: s.link,
    })) : [
      { label: "Patients on Ward",      value: "0", color: "blue",   link: "/patients" },
      { label: "Medications Due",       value: "0", color: "red",    link: "/nurse/mar" },
      { label: "Vitals Recorded Today", value: "0", color: "green",  link: "/patients" },
      { label: "Active Alerts",         value: "0", color: "orange", link: "/alerts" },
    ];

    const handleMarkGiven = (admin: MedicationAdministration) => {
      medMutation.mutate({ id: admin.id, status: "given" });
      notifications.show({
        title: "Medication Administered",
        message: `${admin.prescription_drug_name} recorded as GIVEN for ${admin.patient_name}.`,
        color: "green",
      });
    };

    const dueAdmins = medAdmins?.filter((a) => a.status === "due").slice(0, 5) ?? [];
    const latestHandover = handoversData?.[0] ?? null;

    return (
      <Stack gap="lg">
        {/* Header */}
        <Group justify="space-between" align="center">
            <Box>
              <Title order={2} style={{ fontFamily: "'Bricolage Grotesque', sans-serif", fontWeight: 700, color: "var(--ink)", fontSize: "1.5rem" }}>Nursing Dashboard</Title>
              <Text c="var(--muted)" size="xs">
                Good {greeting()}, {user?.first_name || user?.username} {user?.hospital?.name ? ` · ${user.hospital.name}` : ""}
              </Text>
            </Box>
        </Group>

        {/* Nurse Stats Cards */}
        <SimpleGrid cols={{ base: 2, sm: 4 }} spacing="md">
          {stats.map((stat, i) => (
            <StatCard key={i} stat={stat} />
          ))}
        </SimpleGrid>

        {/* Medications Due Table */}
        <Card withBorder radius="14px" p="md">
          <Group justify="space-between" mb="md">
            <Text className="cardTitle">Medications due</Text>
            <Anchor component={Link} to="/nurse/mar" size="xs">View full MAR →</Anchor>
          </Group>
          <ScrollArea>
            <Table striped>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Patient</Table.Th>
                  <Table.Th>Drug</Table.Th>
                  <Table.Th>Dose</Table.Th>
                  <Table.Th>Due</Table.Th>
                  <Table.Th>Status</Table.Th>
                  <Table.Th>Action</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {loadingMeds && (
                  <Table.Tr>
                    <Table.Td colSpan={6}><Text ta="center" size="sm" c="dimmed">Loading medications due...</Text></Table.Td>
                  </Table.Tr>
                )}
                {!loadingMeds && dueAdmins.length === 0 && (
                  <Table.Tr>
                    <Table.Td colSpan={6}><Text ta="center" size="sm" c="var(--muted)">No pending medications due. All medications are up to date.</Text></Table.Td>
                  </Table.Tr>
                )}
                {!loadingMeds && dueAdmins.map((admin) => {
                  const dueTime = dayjs(admin.scheduled_time).format("HH:mm");
                  return (
                    <Table.Tr key={admin.id}>
                      <Table.Td fw={500}>{admin.patient_name} · {admin.bed_label}</Table.Td>
                      <Table.Td>{admin.prescription_drug_name}</Table.Td>
                      <Table.Td>{admin.prescription_dosage}</Table.Td>
                      <Table.Td>{dueTime}</Table.Td>
                      <Table.Td>
                        <Badge color="red" variant="light">Overdue</Badge>
                      </Table.Td>
                      <Table.Td>
                        <Button
                          size="xs"
                          loading={medMutation.isPending && medMutation.variables?.id === admin.id}
                          onClick={() => handleMarkGiven(admin)}
                        >
                          Mark as given
                        </Button>
                      </Table.Td>
                    </Table.Tr>
                  );
                })}
              </Table.Tbody>
            </Table>
          </ScrollArea>
        </Card>

        {/* Latest Handover */}
        {latestHandover ? (
          <Card withBorder radius="14px" p="md">
            <Group justify="space-between" mb="xs">
              <Text className="cardTitle">Latest handover</Text>
              <Text size="xs" c="dimmed">
                {latestHandover.from_user_name} · {dayjs(latestHandover.created_at).format("HH:mm")}
                {latestHandover.ward_name ? ` · ${latestHandover.ward_name}` : ""}
              </Text>
            </Group>
            <Text size="sm" style={{ whiteSpace: "pre-wrap", lineHeight: 1.6 }}>
              {latestHandover.summary}
            </Text>
            <Button
              variant={latestHandover.acknowledged_at ? "outline" : "filled"}
              color={latestHandover.acknowledged_at ? "gray" : "blue"}
              size="xs"
              mt="md"
              loading={handoverAckMutation.isPending}
              disabled={!!latestHandover.acknowledged_at}
              leftSection={latestHandover.acknowledged_at ? <IconCircleCheck size={14} /> : null}
              onClick={() => handoverAckMutation.mutate(latestHandover.id)}
            >
              {latestHandover.acknowledged_at ? "Handover Acknowledged" : "Acknowledge handover"}
            </Button>
          </Card>
        ) : (
          <Card withBorder radius="14px" p="md">
            <Text className="cardTitle" mb="xs">Latest handover</Text>
            <Text size="sm" c="var(--muted)">No handover notes for this shift. Create a new handover to record notes.</Text>
            <Button component={Link} to="/handovers" variant="subtle" size="xs" mt="md">
              View handovers →
            </Button>
          </Card>
        )}
      </Stack>
    );
  }

  if (role === "lab_technician") {
    const stats = (data?.stats && data.stats.length > 0) ? data.stats.map((s) => ({
      label: s.label,
      value: String(s.value),
      color:
        s.color === "danger"  ? "red"    :
        s.color === "primary" ? "blue"   :
        s.color === "success" ? "green"  :
        s.color === "warning" ? "orange" : s.color,
      delta: s.delta,
      link: s.link,
    })) : [
      { label: "Pending orders",  value: "0", color: "blue",  delta: "—", link: "/lab/orders" },
      { label: "Completed today", value: "0", color: "green", delta: "—", link: "/lab/results" },
      { label: "Critical values", value: "0", color: "red",   delta: "—", link: "/lab/results" },
      { label: "Abnormal rate",   value: "—", color: "amber", delta: "—" },
    ];

    const pendingOrders = labWorklist?.filter((l) => l.status === "pending" || l.status === "in_progress") ?? [];
    const criticalAlert = alertsFeed?.results?.find(
      (a) => (a.kind === "LAB_ABNORMAL" || a.severity === "LIFE_THREAT") && a.is_active
    ) ?? null;
    const labCharts = data?.charts ? Object.entries(data.charts) : [];

    return (
      <Stack gap="lg">
        {/* Critical value alert banner — from real alerts API */}
        {criticalAlert && !criticalNotified && (
          <Alert
            icon={<IconAlertTriangle size={18} />}
            color="danger"
            title="Unnotified Critical Result"
            withCloseButton
            onClose={() => setCriticalNotified(true)}
            styles={{ root: { backgroundColor: "var(--bg-red)", borderColor: "var(--accent-red)", color: "var(--accent-red)" } }}
          >
            <Group justify="space-between" align="center" wrap="nowrap" w="100%">
              <Text size="sm">
                {criticalAlert.label}{criticalAlert.patient_name ? ` — ${criticalAlert.patient_name}` : ""}
              </Text>
              <Button size="xs" color="red" onClick={() => {
                setCriticalNotified(true);
                notifications.show({
                  title: "Alert Acknowledged",
                  message: "Critical lab result has been acknowledged.",
                  color: "green",
                });
              }}>
                Acknowledge
              </Button>
            </Group>
          </Alert>
        )}

        {/* Header */}
        <Group justify="space-between" align="center">
            <Box>
              <Title order={2} style={{ fontFamily: "'Bricolage Grotesque', sans-serif", fontWeight: 700, color: "var(--ink)", fontSize: "1.5rem" }}>Laboratory Dashboard</Title>
              <Text c="var(--muted)" size="xs">
                Good {greeting()}, {user?.first_name || user?.username} {user?.hospital?.name ? ` · ${user.hospital.name}` : ""}
              </Text>
            </Box>
        </Group>

        {/* Lab Stats Cards */}
        <SimpleGrid cols={{ base: 2, sm: 4 }} spacing="md">
          {stats.map((stat, i) => (
            <StatCard key={i} stat={stat} />
          ))}
        </SimpleGrid>

        {/* Pending Orders Worklist */}
        <Card withBorder radius="14px" p="md">
          <Group justify="space-between" mb="md">
            <Text className="cardTitle">Pending orders</Text>
            <Group gap="xs">
              <Badge color="red" variant="filled">{pendingOrders.filter((l) => l.priority === "stat").length} STAT</Badge>
              <Badge color="orange" variant="filled">{pendingOrders.filter((l) => l.priority === "urgent").length} Urgent</Badge>
            </Group>
          </Group>
          <ScrollArea>
            <Table striped highlightOnHover>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Patient</Table.Th>
                  <Table.Th>Test</Table.Th>
                  <Table.Th>Priority</Table.Th>
                  <Table.Th>Ordered by</Table.Th>
                  <Table.Th>Time</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {pendingOrders.length === 0 ? (
                  <Table.Tr>
                    <Table.Td colSpan={5}>
                      <Text ta="center" size="sm" c="var(--muted)" py="md">No pending lab orders. New orders will appear here.</Text>
                    </Table.Td>
                  </Table.Tr>
                ) : (
                  pendingOrders.slice(0, 10).map((l) => {
                    const isStat = l.priority === "stat";
                    return (
                      <Table.Tr
                        key={l.id}
                        onClick={() => navigate(`/patients/${l.patient_nhid}`)}
                        style={{ cursor: "pointer", backgroundColor: isStat ? "var(--bg-red)" : undefined }}
                      >
                        <Table.Td fw={500} style={{ color: isStat ? "var(--accent-red)" : undefined }}>{l.patient_nhid}</Table.Td>
                        <Table.Td style={{ color: isStat ? "var(--accent-red)" : undefined }}>{l.test_name}</Table.Td>
                        <Table.Td>
                          <Badge color={isStat ? "red" : "orange"} variant="filled">{l.priority_display}</Badge>
                        </Table.Td>
                        <Table.Td style={{ color: isStat ? "var(--accent-red)" : undefined }}>{l.ordered_by_name || "—"}</Table.Td>
                        <Table.Td style={{ color: isStat ? "var(--accent-red)" : undefined }}>{dayjs(l.created_at).format("HH:mm")}</Table.Td>
                      </Table.Tr>
                    );
                  })
                )}
              </Table.Tbody>
            </Table>
          </ScrollArea>
        </Card>

        {/* Charts from dashboard API */}
        {labCharts.length > 0 && (
          <SimpleGrid cols={{ base: 1, md: 2 }} spacing="md">
            {labCharts.slice(0, 2).map(([key, chart]) => (
              <ChartPanel key={key} title={key} chart={chart} />
            ))}
          </SimpleGrid>
        )}
      </Stack>
    );
  }

  // ── DEFAULT BACKUP DASHBOARD (super_admin, receptionist) ───────────────────
  const greetingText = greeting();
  const todayDateStr = dayjs().format("dddd, D MMM YYYY");

  return (
    <Stack gap="xl">
      {/* Header */}
      <Group justify="space-between">
        <Box>
          <Title order={2} style={{ fontFamily: "'Bricolage Grotesque', sans-serif", fontWeight: 700, color: "var(--ink)", fontSize: "1.5rem" }}>{ROLE_TITLES[user!.role] ?? "Dashboard"}</Title>
          <Text c="var(--muted)" size="xs">
            Good {greetingText}, {user?.first_name || user?.username} · {user?.hospital?.name || "Central EMR"} · {todayDateStr}
          </Text>
        </Box>
        <Group gap="xs">
          <Button variant="subtle" size="sm" onClick={handleExportPDF} leftSection={<IconDownload size={14} />} color="gray">
            Print / Save PDF
          </Button>
          <Button variant="subtle" size="sm" onClick={() => refetch()} leftSection={<IconRefresh size={16} />} color="gray">
            Refresh
          </Button>
        </Group>
      </Group>

      {/* Quick actions for clinical roles */}
      {user?.is_clinical && (
        <Group>
          <Button component={Link} to="/patients" variant="filled" leftSection={<IconExternalLink size={16} />}>
            Search Patients
          </Button>
        </Group>
      )}

      {/* Stat cards */}
      <SimpleGrid cols={{ base: 2, sm: 4 }} spacing="md">
        {data?.stats.map((stat, i) => (
          <StatCard key={i} stat={stat} />
        ))}
      </SimpleGrid>

      {/* Charts */}
      {data && Object.keys(data.charts).length > 0 && (
        <SimpleGrid cols={{ base: 1, md: 2 }} spacing="md">
          {Object.entries(data.charts).map(([key, chart]) => (
            <ChartPanel
              key={key}
              title={key}
              chart={chart}
            />
          ))}
        </SimpleGrid>
      )}

      {/* Recent encounters */}
      {data?.recent_encounters && data.recent_encounters.length > 0 && (
        <RecentEncountersTable encounters={data.recent_encounters} />
      )}

      {/* Recent labs */}
      {data?.recent_labs && data.recent_labs.length > 0 && (
        <RecentLabsTable labs={data.recent_labs} />
      )}

      {/* Recent audit */}
      {data?.recent_audits && data.recent_audits.length > 0 && (
        <RecentAuditTable entries={data.recent_audits} />
      )}
    </Stack>
  );
}

function DashboardSkeleton() {
  return (
    <Stack gap="xl">
      <Skeleton height={40} width={300} radius="sm" />
      <SimpleGrid cols={{ base: 2, sm: 4 }}>
        {[1,2,3,4].map((i) => <Skeleton key={i} height={100} radius="md" />)}
      </SimpleGrid>
      <SimpleGrid cols={{ base: 1, md: 2 }}>
        {[1,2].map((i) => <Skeleton key={i} height={250} radius="md" />)}
      </SimpleGrid>
    </Stack>
  );
}

function RecentEncountersTable({ encounters }: { encounters: EncounterSummary[] }) {
  const navigate = useNavigate();
  return (
    <Card withBorder radius="14px" padding="lg">
      <Group justify="space-between" mb="md">
        <Group gap="xs">
          <ThemeIcon size={28} color="medsync" variant="light" radius="md">
            <IconArrowLeftRight size={16} />
          </ThemeIcon>
          <Text className="cardTitle" style={{ marginBottom: 0 }}>Recent Encounters</Text>
        </Group>
        <Anchor component={Link} to="/patients" size="sm">View all →</Anchor>
      </Group>
      <ScrollArea>
        <Table striped highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Patient NHID</Table.Th>
              <Table.Th>Patient Name</Table.Th>
              <Table.Th>Type</Table.Th>
              <Table.Th>Hospital</Table.Th>
              <Table.Th>Date</Table.Th>
              <Table.Th>Flags</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {encounters.map((enc) => (
              <Table.Tr
                key={enc.id}
                onClick={() => navigate(`/patients/${enc.patient_nhid}`)}
                style={{ cursor: "pointer" }}
              >
                <Table.Td>
                  <Text size="sm" ff="monospace">{enc.patient_nhid}</Text>
                </Table.Td>
                <Table.Td fw={500}>{enc.patient_name}</Table.Td>
                <Table.Td>
                  <Badge variant="light" size="sm">{enc.encounter_type_display}</Badge>
                </Table.Td>
                <Table.Td>
                  {enc.created_at_hospital?.name ?? "—"}
                  {enc.is_cross_hospital && (
                    <Badge color="yellow" size="xs" ml={4} leftSection={<IconArrowLeftRight size={10} />}>
                      External
                    </Badge>
                  )}
                </Table.Td>
                <Table.Td>
                  <Text size="sm">{dayjs(enc.created_at).fromNow()}</Text>
                </Table.Td>
                <Table.Td>
                  <Group gap={4} wrap="nowrap">
                    {enc.has_abnormal_labs && (
                      <Badge color="red" size="xs" leftSection={<IconAlertTriangle size={10} />}>
                        Abnormal lab
                      </Badge>
                    )}
                    {enc.encounter_type === "EMRG" && (
                      <Badge color="red" size="xs" leftSection={<IconUrgent size={10} />}>
                        Emergency
                      </Badge>
                    )}
                    {enc.encounter_type === "FU" && (
                      <Badge color="blue" size="xs" leftSection={<IconCircleCheck size={10} />}>
                        Follow-up
                      </Badge>
                    )}
                  </Group>
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </ScrollArea>
    </Card>
  );
}

function RecentLabsTable({ labs }: { labs: (LabResult & { patient_name?: string })[] }) {
  return (
    <Card withBorder radius="14px" padding="lg">
      <Group gap="xs" mb="md">
        <ThemeIcon size={28} color="medsync" variant="light" radius="md">
          <IconAlertTriangle size={16} />
        </ThemeIcon>
        <Text className="cardTitle" style={{ marginBottom: 0 }}>Recent Lab Results</Text>
      </Group>
      <ScrollArea>
        <Table striped highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Patient</Table.Th>
              <Table.Th>Test</Table.Th>
              <Table.Th>Status</Table.Th>
              <Table.Th>Date</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {labs.map((lab) => (
              <Table.Tr key={lab.id}>
                <Table.Td>
                  <Anchor component={Link} to={`/patients/${lab.patient_nhid}`} size="sm">
                    {lab.patient_name || lab.patient_nhid}
                  </Anchor>
                </Table.Td>
                <Table.Td>{lab.test_name}</Table.Td>
                <Table.Td>
                  <Badge color={lab.is_abnormal ? "red" : "green"} size="sm">
                    {lab.is_abnormal ? "Abnormal" : "Normal"}
                  </Badge>
                </Table.Td>
                <Table.Td>{dayjs(lab.created_at).fromNow()}</Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </ScrollArea>
    </Card>
  );
}

function RecentAuditTable({ entries }: { entries: AuditLogEntry[] }) {
  return (
    <Card withBorder radius="14px" padding="lg">
      <Group justify="space-between" mb="md">
        <Group gap="xs">
          <ThemeIcon size={28} color="medsync" variant="light" radius="md">
            <IconExternalLink size={16} />
          </ThemeIcon>
          <Text className="cardTitle" style={{ marginBottom: 0 }}>Recent Audit Events</Text>
        </Group>
        <Anchor component={Link} to="/admin/audit-logs" size="sm">Full audit log →</Anchor>
      </Group>
      <ScrollArea>
        <Table striped highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Actor</Table.Th>
              <Table.Th>Action</Table.Th>
              <Table.Th>Patient</Table.Th>
              <Table.Th>Cross-Hospital</Table.Th>
              <Table.Th>Time</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {entries.map((entry) => (
              <Table.Tr key={entry.id} bg={entry.is_cross_hospital ? "var(--bg-amber)" : undefined}>
                <Table.Td>
                  <Text size="sm" fw={600}>{entry.actor_username}</Text>
                  <Text size="xs" c="dimmed">{entry.actor_role}</Text>
                </Table.Td>
                <Table.Td>
                  <Badge variant="light" size="sm">{entry.action_display}</Badge>
                </Table.Td>
                <Table.Td>
                  {entry.patient_nhid ? (
                    <Anchor component={Link} to={`/patients/${entry.patient_nhid}`} size="sm" ff="monospace">
                      {entry.patient_nhid}
                    </Anchor>
                  ) : "—"}
                </Table.Td>
                <Table.Td>
                  {entry.is_cross_hospital && (
                    <Badge color="yellow" size="xs" leftSection={<IconArrowLeftRight size={10} />}>
                      YES
                    </Badge>
                  )}
                </Table.Td>
                <Table.Td>{dayjs(entry.timestamp).fromNow()}</Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </ScrollArea>
    </Card>
  );
}

function greeting(): string {
  const h = new Date().getHours();
  if (h < 12) return "morning";
  if (h < 17) return "afternoon";
  return "evening";
}
