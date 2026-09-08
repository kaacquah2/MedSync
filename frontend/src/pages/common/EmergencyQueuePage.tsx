import {
  Alert,
  Anchor,
  Badge,
  Button,
  Card,
  Group,
  Modal,
  Select,
  SimpleGrid,
  Skeleton,
  Stack,
  Table,
  Text,
  Textarea,
  ThemeIcon,
} from "@mantine/core";
import { PageHeader } from "@/components/PageHeader";
import { useForm } from "@mantine/form";
import { useDisclosure } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import {
  IconAlertTriangle,
  IconCheck,
  IconClock,
  IconPlus,
  IconRefresh,
  IconSearch,
  IconStethoscope,
  IconUrgent,
} from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import dayjs from "dayjs";
import relativeTime from "dayjs/plugin/relativeTime";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  appointmentAction,
  createAppointment,
  fetchAppointments,
  searchPatients,
} from "@/api/endpoints";
import { useAuth } from "@/auth/AuthProvider";
import type { Appointment, TriageAcuity } from "@/types";

dayjs.extend(relativeTime);

export type TriageDisplayLevel = TriageAcuity | "UNTRIAGED";

export const TRIAGE_COLORS: Record<TriageDisplayLevel, string> = {
  RED: "red",
  ORANGE: "orange",
  YELLOW: "yellow",
  GREEN: "green",
  UNTRIAGED: "red",
};

interface ApiErrorResponse {
  response?: {
    data?: {
      error?: string;
    };
  };
}

export interface TriageInfo {
  level: TriageDisplayLevel;
  notes: string;
  isUntriaged: boolean;
}

export function parseTriage(appt: Appointment): TriageInfo {
  // 1. Dedicated first-class backend enum field triage_acuity
  if (appt.triage_acuity && ["RED", "ORANGE", "YELLOW", "GREEN"].includes(appt.triage_acuity)) {
    const rawNotes = appt.notes || appt.reason || "";
    const cleanNotes = rawNotes.replace(/^\[Triage:\s*(?:RED|ORANGE|YELLOW|GREEN)\]\s*/i, "").trim();
    return {
      level: appt.triage_acuity,
      notes: cleanNotes || rawNotes,
      isUntriaged: false,
    };
  }

  if (appt.triage_level && ["RED", "ORANGE", "YELLOW", "GREEN"].includes(appt.triage_level)) {
    const rawNotes = appt.notes || appt.reason || "";
    const cleanNotes = rawNotes.replace(/^\[Triage:\s*(?:RED|ORANGE|YELLOW|GREEN)\]\s*/i, "").trim();
    return {
      level: appt.triage_level,
      notes: cleanNotes || rawNotes,
      isUntriaged: false,
    };
  }

  // 2. Legacy fallback for older unmigrated appointments
  const text = appt.notes || appt.reason || "";
  const match = text.match(/^\[Triage:\s*(RED|ORANGE|YELLOW|GREEN)\]\s*(.*)$/i);
  if (match) {
    return {
      level: match[1].toUpperCase() as TriageAcuity,
      notes: match[2].trim(),
      isUntriaged: false,
    };
  }

  // 3. CLINICAL SAFETY GUARD:
  // In an emergency room, an unclassified emergency arrival must NEVER be silently downgraded to GREEN.
  // Silently defaulting to GREEN risks fatal delay for dying patients.
  // Treat missing/corrupted triage classifications as UNTRIAGED with top clinical evaluation priority.
  return {
    level: "UNTRIAGED",
    notes: text,
    isUntriaged: true,
  };
}

export function formatTriage(level: TriageAcuity, notes: string): string {
  return `[Triage: ${level}] ${notes.trim()}`;
}

export function EmergencyQueuePage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [opened, { open, close }] = useDisclosure(false);
  const [patientSearch, setPatientSearch] = useState("");

  const { data: checkedIn, isLoading: loadingCheckedIn, refetch } = useQuery({
    queryKey: ["emergency-queue-checked-in"],
    queryFn: () => fetchAppointments({ status: "checked_in" }).then((r) => r.data),
    refetchInterval: 15_000,
  });

  const { data: inProgress, isLoading: loadingInProgress } = useQuery({
    queryKey: ["emergency-queue-in-progress"],
    queryFn: () => fetchAppointments({ status: "in_progress" }).then((r) => r.data),
    refetchInterval: 15_000,
  });

  const allEmergency = [
    ...(checkedIn ?? []),
    ...(inProgress ?? []),
  ].filter((a) => a.appointment_type === "emergency");

  const { data: searchData, isLoading: searching } = useQuery({
    queryKey: ["emergency-patient-search", patientSearch],
    queryFn: () => searchPatients(patientSearch).then((r) => r.data),
    enabled: patientSearch.length >= 2,
  });

  const patientOptions = searchData?.results.map((p) => ({
    value: p.universal_id,
    label: `${p.full_name} — ${p.universal_id}`,
  })) ?? [];

  const form = useForm({
    initialValues: {
      patient_nhid: "",
      triage_level: "YELLOW" as TriageAcuity,
      triage_notes: "",
    },
    validate: {
      patient_nhid: (v) => (v ? null : "Please select a patient"),
      triage_notes: (v) => (v.trim() ? null : "Please enter triage clinical notes"),
    },
  });

  const createMutation = useMutation({
    mutationFn: (values: typeof form.values) => {
      const triageStr = formatTriage(values.triage_level, values.triage_notes);
      return createAppointment({
        patient: values.patient_nhid,
        appointment_type: "emergency",
        status: "checked_in",
        scheduled_for: new Date().toISOString(),
        triage_acuity: values.triage_level,
        triage_level: values.triage_level,
        reason: values.triage_notes.trim(),
        notes: triageStr,
      });
    },
    onSuccess: () => {
      notifications.show({
        color: "green",
        icon: <IconCheck size={16} />,
        message: "Patient added to emergency queue.",
      });
      form.reset();
      setPatientSearch("");
      close();
      refetch();
    },
    onError: (err: unknown) => {
      notifications.show({
        color: "red",
        message: (err as ApiErrorResponse)?.response?.data?.error || "Failed to add patient to queue.",
      });
    },
  });

  const actionMutation = useMutation({
    mutationFn: ({ id, action }: { id: number; action: string }) =>
      appointmentAction(id, action),
    onSuccess: (resp, variables) => {
      qc.invalidateQueries({ queryKey: ["emergency-queue-checked-in"] });
      qc.invalidateQueries({ queryKey: ["emergency-queue-in-progress"] });
      if (variables.action === "start") {
        const triage = parseTriage(resp.data);
        navigate(`/patients/${resp.data.patient_nhid}/encounters/new?type=EMRG&chief_complaint=${encodeURIComponent(triage.notes)}&appt_id=${resp.data.id}`);
      } else {
        notifications.show({
          color: "green",
          icon: <IconCheck size={16} />,
          message: `Queue item updated successfully.`,
        });
      }
    },
    onError: (err: unknown) => {
      notifications.show({
        color: "red",
        message: (err as ApiErrorResponse)?.response?.data?.error || "Failed to update queue item.",
      });
    },
  });

  const sortedQueue = [...allEmergency].sort((a, b) => {
    // UNTRIAGED = 5 (Immediate mandatory evaluation)
    // RED = 4 (Resuscitation)
    // ORANGE = 3 (Emergent)
    // YELLOW = 2 (Urgent)
    // GREEN = 1 (Non-urgent)
    const levelScore: Record<TriageDisplayLevel, number> = {
      UNTRIAGED: 5,
      RED: 4,
      ORANGE: 3,
      YELLOW: 2,
      GREEN: 1,
    };
    const aTriage = parseTriage(a);
    const bTriage = parseTriage(b);
    const scoreDiff = levelScore[bTriage.level] - levelScore[aTriage.level];
    if (scoreDiff !== 0) return scoreDiff;
    return dayjs(a.scheduled_for).diff(dayjs(b.scheduled_for));
  });

  const untriagedCount = allEmergency.filter((a) => parseTriage(a).isUntriaged).length;
  const redCount = allEmergency.filter((a) => parseTriage(a).level === "RED").length;
  const orangeCount = allEmergency.filter((a) => parseTriage(a).level === "ORANGE").length;
  const activeCount = allEmergency.filter((a) => a.status === "checked_in").length;

  return (
    <Stack gap="lg">
      <PageHeader
        icon={<IconUrgent size={20} />}
        title="Emergency Queue & Triage"
        subtitle="Real-time triage board — auto-refreshes every 15 s"
      >
        <Button
          leftSection={<IconRefresh size={14} />}
          variant="subtle"
          size="sm"
          color="gray"
          onClick={() => refetch()}
          loading={loadingCheckedIn || loadingInProgress}
        >
          Refresh
        </Button>
        <Button
          leftSection={<IconPlus size={16} />}
          color="red"
          size="sm"
          onClick={open}
        >
          Admit Emergency Patient
        </Button>
      </PageHeader>

      {untriagedCount > 0 && (
        <Alert
          color="red"
          icon={<IconAlertTriangle size={20} />}
          title="Clinical Safety Warning — Untriaged Emergency Patients"
          radius="md"
        >
          {untriagedCount} patient(s) in the emergency queue have missing or unverified triage classifications.
          Emergency clinical protocol requires immediate assessment by a triage officer to prevent adverse outcomes.
        </Alert>
      )}

      <SimpleGrid cols={{ base: 1, sm: untriagedCount > 0 ? 4 : 3 }} spacing="md">
        {untriagedCount > 0 && (
          <Card withBorder radius="md" p="md" style={{ borderLeft: "4px solid var(--mantine-color-red-9)", background: "var(--mantine-color-red-0)" }}>
            <Text size="xs" tt="uppercase" fw={700} c="red">Untriaged / Immediate</Text>
            <Text size="xl" fw={800} c="red">{untriagedCount} waiting</Text>
          </Card>
        )}
        <Card withBorder radius="md" p="md" style={{ borderLeft: "4px solid var(--mantine-color-red-6)" }}>
          <Text size="xs" tt="uppercase" fw={700} c="dimmed">Critical (RED)</Text>
          <Text size="xl" fw={800} c="red">{redCount} waiting</Text>
        </Card>
        <Card withBorder radius="md" p="md" style={{ borderLeft: "4px solid var(--mantine-color-orange-6)" }}>
          <Text size="xs" tt="uppercase" fw={700} c="dimmed">Emergent (ORANGE)</Text>
          <Text size="xl" fw={800} c="orange">{orangeCount} waiting</Text>
        </Card>
        <Card withBorder radius="md" p="md" style={{ borderLeft: "4px solid var(--mantine-color-blue-6)" }}>
          <Text size="xs" tt="uppercase" fw={700} c="dimmed">Active Waiting Queue</Text>
          <Text size="xl" fw={800} c="blue">{activeCount} patients</Text>
        </Card>
      </SimpleGrid>

      {loadingCheckedIn && loadingInProgress ? (
        <Stack gap="xs">
          <Skeleton height={50} />
          <Skeleton height={50} />
          <Skeleton height={50} />
        </Stack>
      ) : sortedQueue.length === 0 ? (
        <Card withBorder radius="md" p="xl" ta="center">
          <ThemeIcon size={48} radius="xl" color="gray" variant="light" mx="auto" mb="sm">
            <IconClock size={24} />
          </ThemeIcon>
          <Text fw={700}>Emergency Queue is Empty</Text>
          <Text size="sm" c="dimmed" mt={4}>
            There are currently no patients waiting in the emergency queue.
          </Text>
        </Card>
      ) : (
        <Card withBorder radius="md" p={0}>
          <Table.ScrollContainer minWidth={800}>
            <Table striped highlightOnHover verticalSpacing="sm" withTableBorder withColumnBorders>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th style={{ width: 150 }}>Triage Level</Table.Th>
                  <Table.Th>Patient</Table.Th>
                  <Table.Th>National Health ID</Table.Th>
                  <Table.Th>Wait Time</Table.Th>
                  <Table.Th>Triage Complaint / Notes</Table.Th>
                  <Table.Th style={{ width: 220 }}>Actions</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {sortedQueue.map((appt) => {
                  const triage = parseTriage(appt);
                  const waitMins = dayjs().diff(dayjs(appt.scheduled_for), "minute");
                  const color = TRIAGE_COLORS[triage.level];
                  const isClinical = user?.role === "doctor" || user?.role === "nurse";

                  return (
                    <Table.Tr
                      key={appt.id}
                      bg={
                        triage.isUntriaged
                          ? "var(--bg-red)"
                          : triage.level === "RED"
                          ? "var(--bg-red)"
                          : triage.level === "ORANGE"
                          ? "var(--bg-amber)"
                          : undefined
                      }
                    >
                      <Table.Td>
                        {triage.isUntriaged ? (
                          <Badge
                            color="red"
                            variant="filled"
                            fullWidth
                            size="md"
                            leftSection={<IconAlertTriangle size={12} />}
                          >
                            UNTRIAGED
                          </Badge>
                        ) : (
                          <Badge color={color} variant="filled" fullWidth size="md">
                            {triage.level}
                          </Badge>
                        )}
                      </Table.Td>
                      <Table.Td>
                        <Anchor component={Link} to={`/patients/${appt.patient_nhid}`} fw={600}>
                          {appt.patient_name}
                        </Anchor>
                      </Table.Td>
                      <Table.Td>
                        <Text size="xs" ff="monospace" c="blue" fw={600}>
                          {appt.patient_nhid}
                        </Text>
                      </Table.Td>
                      <Table.Td>
                        <Group gap={6}>
                          <IconClock size={14} style={{ color: waitMins > 20 ? "var(--mantine-color-red-6)" : "inherit" }} />
                          <Text size="sm" fw={waitMins > 20 ? 700 : 500} c={waitMins > 20 ? "red" : undefined}>
                            {dayjs(appt.scheduled_for).fromNow(true)}
                          </Text>
                        </Group>
                      </Table.Td>
                      <Table.Td>
                        <Text size="sm" lineClamp={2} style={{ whiteSpace: "pre-line" }}>
                          {triage.notes}
                        </Text>
                      </Table.Td>
                      <Table.Td>
                        <Group gap="xs" wrap="nowrap">
                          {appt.status === "checked_in" && isClinical && (
                            <Button
                              size="xs"
                              color="blue"
                              leftSection={<IconStethoscope size={12} />}
                              onClick={() => actionMutation.mutate({ id: appt.id, action: "start" })}
                            >
                              Treat Patient
                            </Button>
                          )}
                          {appt.status === "in_progress" && (
                            <Badge color="violet" variant="light" size="sm">
                              In treatment
                            </Badge>
                          )}
                          <Button
                            size="xs"
                            variant="light"
                            color="gray"
                            onClick={() => actionMutation.mutate({ id: appt.id, action: "cancel" })}
                          >
                            Dismiss
                          </Button>
                        </Group>
                      </Table.Td>
                    </Table.Tr>
                  );
                })}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        </Card>
      )}

      <Modal opened={opened} onClose={close} title="Admit to Emergency Triage" size="md">
        <form onSubmit={form.onSubmit((v) => createMutation.mutate(v))}>
          <Stack gap="md">
            <Select
              label="Select Patient"
              placeholder="Search by NHID or name..."
              leftSection={<IconSearch size={16} />}
              searchable
              required
              data={patientOptions}
              onSearchChange={setPatientSearch}
              nothingFoundMessage={patientSearch.length < 2 ? "Type name or NHID (min 2 chars)" : searching ? "Searching..." : "No patients found"}
              {...form.getInputProps("patient_nhid")}
            />

            <Select
              label="Triage Severity Level"
              placeholder="Select triage level"
              required
              data={[
                { value: "RED", label: "RED — Resuscitation (Immediate life threat)" },
                { value: "ORANGE", label: "ORANGE — Emergent (Very urgent, high risk)" },
                { value: "YELLOW", label: "YELLOW — Urgent (Stable but requires urgent care)" },
                { value: "GREEN", label: "GREEN — Standard (Non-urgent / minor complaints)" },
              ]}
              {...form.getInputProps("triage_level")}
            />

            <Textarea
              label="Presenting Complaint / Triage Notes"
              placeholder="Describe presenting symptoms, pain score, trauma details, etc."
              rows={4}
              required
              {...form.getInputProps("triage_notes")}
            />

            <Group justify="flex-end" mt="md">
              <Button variant="light" color="gray" onClick={close}>Cancel</Button>
              <Button type="submit" color="red" loading={createMutation.isPending}>
                Admit to Emergency
              </Button>
            </Group>
          </Stack>
        </form>
      </Modal>
    </Stack>
  );
}
