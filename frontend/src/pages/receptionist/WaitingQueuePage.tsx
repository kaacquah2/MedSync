/**
 * WaitingQueuePage — live waiting queue for receptionists.
 * Shows today's checked-in appointments with auto-updating wait times.
 * Orange >30 min, red >60 min.
 */

import {
  Badge,
  Box,
  Button,
  Card,
  Group,
  Progress,
  Skeleton,
  Stack,
  Table,
  Text,
  ThemeIcon,
  Title,
} from "@mantine/core";
import { IconClock, IconRefresh, IconUrgent } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import dayjs from "dayjs";
import { useEffect, useState } from "react";
import { fetchAppointments } from "@/api/endpoints";
import type { Appointment } from "@/types";


function formatWait(mins: number): string {
  if (mins < 0)   return "Upcoming";
  if (mins < 60)  return `${mins}m`;
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  return `${h}h ${m}m`;
}

function waitColor(mins: number): string {
  if (mins < 0)   return "blue";
  if (mins < 30)  return "green";
  if (mins < 60)  return "orange";
  return "red";
}

const APPT_TYPE_COLORS: Record<string, string> = {
  outpatient: "blue",
  follow_up:  "cyan",
  procedure:  "violet",
  lab:        "teal",
  emergency:  "red",
};

export function WaitingQueuePage() {
  const [now, setNow] = useState(dayjs());

  // Tick every 30 seconds to update wait times
  useEffect(() => {
    const t = setInterval(() => setNow(dayjs()), 30_000);
    return () => clearInterval(t);
  }, []);

  const { data: appointments, isLoading, refetch } = useQuery({
    queryKey: ["waiting-queue"],
    queryFn:  () => fetchAppointments({ status: "checked_in" }).then((r) => r.data),
    refetchInterval: 60_000,
  });

  // Also include scheduled for today that haven't started
  const { data: scheduledToday } = useQuery({
    queryKey: ["waiting-queue-scheduled"],
    queryFn:  () => fetchAppointments({ status: "scheduled" }).then((r) => r.data),
    refetchInterval: 60_000,
  });

  const todayStart = dayjs().startOf("day").toISOString();
  const todayEnd   = dayjs().endOf("day").toISOString();

  const allAppointments: Appointment[] = [
    ...(appointments ?? []),
    ...(scheduledToday ?? []).filter((a) =>
      a.scheduled_for >= todayStart && a.scheduled_for <= todayEnd
    ),
  ];

  const sorted = [...allAppointments].sort((a, b) =>
    dayjs(a.scheduled_for).diff(dayjs(b.scheduled_for))
  );

  const waiting   = allAppointments.filter((a) => a.status === "checked_in").length;
  const over30    = allAppointments.filter((a) => {
    const mins = dayjs().diff(dayjs(a.scheduled_for), "minute");
    return a.status === "checked_in" && mins >= 30;
  }).length;

  return (
    <Stack gap="lg">
      <Group justify="space-between">
        <Group gap="xs">
          <ThemeIcon size={36} color="medsync" variant="light" radius="md">
            <IconClock size={20} />
          </ThemeIcon>
          <Box>
            <Title order={2}>Live Waiting Queue</Title>
            <Text size="xs" c="dimmed">
              {dayjs().format("dddd, DD MMMM YYYY")} · Updates every 30s
            </Text>
          </Box>
        </Group>
        <Button leftSection={<IconRefresh size={16} />} variant="subtle" size="sm" onClick={() => refetch()}>
          Refresh
        </Button>
      </Group>

      {/* Summary cards */}
      <Group gap="md">
        {[
          { label: "Total today",  value: sorted.length, color: "blue" },
          { label: "Waiting now",  value: waiting,       color: "orange" },
          { label: "Waiting >30m", value: over30,        color: "red" },
        ].map((c) => (
          <Card key={c.label} withBorder radius="md" p="md" miw={130}
            style={{ borderLeftWidth: 3, borderLeftColor: `var(--mantine-color-${c.color}-5)` }}
          >
            <Text size="xs" tt="uppercase" fw={700} c="dimmed">{c.label}</Text>
            <Text size="xl" fw={800} c={c.color}>{c.value}</Text>
          </Card>
        ))}
      </Group>

      {/* Queue progress */}
      {sorted.length > 0 && (
        <Card withBorder radius="md" p="md">
          <Group justify="space-between" mb="xs">
            <Text size="sm" fw={600}>Queue Progress</Text>
            <Text size="xs" c="dimmed">
              {allAppointments.filter((a) => a.status === "completed").length} completed today
            </Text>
          </Group>
          <Progress
            value={sorted.length > 0
              ? (allAppointments.filter((a) => a.status === "completed").length / sorted.length) * 100
              : 0
            }
            color="green"
            size="md"
            radius="xl"
          />
        </Card>
      )}

      {isLoading ? (
        <Stack gap="xs">{[1,2,3,4,5].map((i) => <Skeleton key={i} height={56} />)}</Stack>
      ) : !sorted.length ? (
        <Box ta="center" py="xl">
          <Text c="dimmed">No appointments scheduled for today.</Text>
        </Box>
      ) : (
        <Card withBorder radius="md" p={0}>
          <Table.ScrollContainer minWidth={800}>
            <Table striped highlightOnHover withTableBorder withColumnBorders>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>#</Table.Th>
                  <Table.Th>Patient</Table.Th>
                  <Table.Th>NHID</Table.Th>
                  <Table.Th>Type</Table.Th>
                  <Table.Th>Scheduled</Table.Th>
                  <Table.Th>Wait time</Table.Th>
                  <Table.Th>Doctor</Table.Th>
                  <Table.Th>Status</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {sorted.map((appt, i) => {
                  const mins     = dayjs(now).diff(dayjs(appt.scheduled_for), "minute");
                  const wColor   = waitColor(mins);
                  const isUrgent = appt.appointment_type === "emergency";
                  return (
                    <Table.Tr
                      key={appt.id}
                      bg={
                        mins >= 60 ? "var(--bg-red)"
                        : mins >= 30 ? "var(--bg-amber)"
                        : undefined
                      }
                    >
                      <Table.Td>
                        <Text size="sm" fw={600} c="dimmed">
                          {isUrgent && <IconUrgent size={14} style={{ marginRight: 4, color: "var(--mantine-color-red-6)" }} />}
                          {i + 1}
                        </Text>
                      </Table.Td>
                      <Table.Td><Text size="sm" fw={500}>{appt.patient_name}</Text></Table.Td>
                      <Table.Td>
                        <Text size="xs" ff="monospace" c="blue">{appt.patient_nhid}</Text>
                      </Table.Td>
                      <Table.Td>
                        <Badge
                          color={APPT_TYPE_COLORS[appt.appointment_type] ?? "gray"}
                          variant="light"
                          size="sm"
                        >
                          {appt.appointment_type_display}
                        </Badge>
                      </Table.Td>
                      <Table.Td>
                        <Text size="sm">{dayjs(appt.scheduled_for).format("HH:mm")}</Text>
                        <Text size="xs" c="dimmed">{dayjs(appt.scheduled_for).format("DD MMM")}</Text>
                      </Table.Td>
                      <Table.Td>
                        <Badge color={wColor} variant={mins >= 60 ? "filled" : "light"} size="sm">
                          {formatWait(mins)}
                        </Badge>
                      </Table.Td>
                      <Table.Td>
                        <Text size="sm">{appt.provider_name ?? "—"}</Text>
                      </Table.Td>
                      <Table.Td>
                        <Badge
                          color={
                            appt.status === "checked_in" ? "blue"
                            : appt.status === "in_progress" ? "violet"
                            : appt.status === "completed" ? "green"
                            : appt.status === "no_show" ? "red"
                            : "gray"
                          }
                          variant="light"
                          size="sm"
                        >
                          {appt.status_display}
                        </Badge>
                      </Table.Td>
                    </Table.Tr>
                  );
                })}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        </Card>
      )}
    </Stack>
  );
}
