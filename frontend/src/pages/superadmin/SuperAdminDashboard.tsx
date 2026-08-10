/**
 * Super-Admin Dashboard — system-wide KPIs, audit activity, hospital health.
 * Served at /superadmin (role-gated: super_admin only).
 */

import {
  Anchor,
  Badge,
  Box,
  Button,
  Card,
  Center,
  Group,
  Paper,
  ScrollArea,
  SimpleGrid,
  Skeleton,
  Stack,
  Table,
  Text,
  ThemeIcon,
  Title,
} from "@mantine/core";
import {
  IconActivity,
  IconBuilding,
  IconRefresh,
  IconShieldCheck,
  IconUsers,
} from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import dayjs from "dayjs";
import relativeTime from "dayjs/plugin/relativeTime";
import { Link } from "react-router-dom";
import { fetchDashboard } from "@/api/endpoints";
import { useAuth } from "@/auth/AuthProvider";
import { ChartPanel } from "@/pages/dashboard/ChartPanel";
import { StatCard } from "@/pages/dashboard/StatCard";

dayjs.extend(relativeTime);

export function SuperAdminDashboard() {
  const { user } = useAuth();
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["dashboard-superadmin"],
    queryFn: () => fetchDashboard().then((r) => r.data),
    staleTime: 60_000,
    refetchInterval: 60_000,
  });

  if (isLoading) {
    return (
      <Stack gap="xl">
        <Skeleton height={60} radius="sm" />
        <SimpleGrid cols={{ base: 2, sm: 4 }}>
          {[1, 2, 3, 4].map((i) => <Skeleton key={i} height={110} radius="md" />)}
        </SimpleGrid>
        <SimpleGrid cols={{ base: 1, md: 2 }}>
          {[1, 2].map((i) => <Skeleton key={i} height={260} radius="md" />)}
        </SimpleGrid>
      </Stack>
    );
  }

  if (error) {
    return (
      <Center h={300}>
        <Stack align="center" gap="sm">
          <Text c="red">Failed to load dashboard.</Text>
          <Button leftSection={<IconRefresh size={16} />} onClick={() => refetch()} variant="light">
            Retry
          </Button>
        </Stack>
      </Center>
    );
  }

  return (
    <Stack gap="xl">
      {/* Header */}
      <Group justify="space-between">
        <Box>
          <Title order={2} style={{ fontFamily: "'Bricolage Grotesque', sans-serif", fontWeight: 700, color: "var(--ink)", fontSize: "1.5rem" }}>System Administration</Title>
          <Text c="var(--muted)" size="sm">
            Welcome back, {user?.first_name || user?.username} · System-wide overview
          </Text>
        </Box>
        <Button leftSection={<IconRefresh size={16} />} variant="subtle" size="sm" onClick={() => refetch()}>
          Refresh
        </Button>
      </Group>

      {/* KPI stat cards */}
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
              title={CHART_TITLES[key] ?? key}
              chart={chart}
            />
          ))}
        </SimpleGrid>
      )}

      {/* Audit activity + Quick links */}
      <SimpleGrid cols={{ base: 1, md: 3 }} spacing="md">
        {/* Recent audit events — 2/3 width */}
        <Card withBorder radius="14px" padding="lg" style={{ gridColumn: "span 2" }}>
          <Group justify="space-between" mb="md">
            <Group gap="xs">
              <ThemeIcon size={28} color="medsync" variant="light" radius="md">
                <IconActivity size={16} />
              </ThemeIcon>
              <Text className="cardTitle" style={{ marginBottom: 0 }}>Recent Audit Events</Text>
            </Group>
            <Anchor component={Link} to="/superadmin/audit-logs" size="sm">
              Full log →
            </Anchor>
          </Group>
          <ScrollArea>
            <Table striped withTableBorder withColumnBorders>
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
                {(data?.recent_audits ?? []).map((entry) => (
                  <Table.Tr
                    key={entry.id}
                    bg={entry.is_cross_hospital ? "yellow.0" : undefined}
                  >
                    <Table.Td>
                      <Text size="sm" fw={600}>{entry.actor_username}</Text>
                      <Text size="xs" c="dimmed">{entry.actor_role}</Text>
                    </Table.Td>
                    <Table.Td>
                      <Badge variant="light" size="sm">{entry.action_display}</Badge>
                    </Table.Td>
                    <Table.Td>
                      {entry.patient_nhid ? (
                        <Anchor
                          component={Link}
                          to={`/patients/${entry.patient_nhid}`}
                          size="sm"
                          ff="monospace"
                        >
                          {entry.patient_nhid}
                        </Anchor>
                      ) : "—"}
                    </Table.Td>
                    <Table.Td>
                      {entry.is_cross_hospital && (
                        <Badge color="yellow" size="xs">YES</Badge>
                      )}
                    </Table.Td>
                    <Table.Td>
                      <Text size="xs">{dayjs(entry.timestamp).fromNow()}</Text>
                    </Table.Td>
                  </Table.Tr>
                ))}
                {!data?.recent_audits?.length && (
                  <Table.Tr>
                    <Table.Td colSpan={5}>
                      <Text ta="center" c="dimmed" size="sm" py="md">
                        No recent audit events.
                      </Text>
                    </Table.Td>
                  </Table.Tr>
                )}
              </Table.Tbody>
            </Table>
          </ScrollArea>
        </Card>

        {/* Quick links — 1/3 width */}
        <Stack gap="sm">
          <Text className="cardTitle" style={{ marginBottom: 4 }}>Quick Actions</Text>
          {[
            { label: "All Hospitals",      to: "/superadmin/hospitals",       icon: <IconBuilding size={18} /> },
            { label: "Audit Logs",         to: "/superadmin/audit-logs",      icon: <IconActivity size={18} /> },
            { label: "Break-Glass Review", to: "/superadmin/break-glass-review", icon: <IconShieldCheck size={18} /> },
            { label: "User Management",    to: "/superadmin/user-management", icon: <IconUsers size={18} /> },
          ].map((link) => (
            <Paper key={link.to} withBorder p="sm" radius="14px">
              <Anchor component={Link} to={link.to} underline="never">
                <Group gap="sm">
                  <ThemeIcon size={32} color="medsync" variant="light" radius="md">
                    {link.icon}
                  </ThemeIcon>
                  <Text size="sm" fw={500}>{link.label}</Text>
                </Group>
              </Anchor>
            </Paper>
          ))}
        </Stack>
      </SimpleGrid>
    </Stack>
  );
}

const CHART_TITLES: Record<string, string> = {
  enc_trend:   "Encounter Trend (14 days)",
  cross_trend: "Cross-Hospital Events (14 days)",
  hosp_dist:   "Top Hospitals by Encounters",
  enc_type:    "Encounter Types",
};
