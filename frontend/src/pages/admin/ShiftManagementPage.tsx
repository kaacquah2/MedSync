/**
 * ShiftManagementPage — hospital admin shift record list.
 * Shows ShiftRecord list for the hospital with end-shift action.
 */

import {
  Badge,
  Box,
  Button,
  Card,
  Group,
  Skeleton,
  Stack,
  Table,
  Text,
  ThemeIcon,
  Title,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconCheck, IconClock, IconPlayerStop } from "@tabler/icons-react";
import { modals } from "@mantine/modals";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import dayjs from "dayjs";
import duration from "dayjs/plugin/duration";
import { endShift, fetchShifts } from "@/api/endpoints";

dayjs.extend(duration);

function formatDuration(start: string, end?: string): string {
  const s = dayjs(start);
  const e = end ? dayjs(end) : dayjs();
  const diff = dayjs.duration(e.diff(s));
  const hrs  = Math.floor(diff.asHours());
  const mins = diff.minutes();
  return `${hrs}h ${mins}m`;
}

export function ShiftManagementPage() {
  const qc = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ["shifts-admin"],
    queryFn:  () => fetchShifts().then((r) => r.data),
    refetchInterval: 60_000,
  });

  const endMutation = useMutation({
    mutationFn: (id: number) => endShift(id),
    onSuccess: () => {
      notifications.show({ color: "green", icon: <IconCheck />, message: "Shift ended." });
      qc.invalidateQueries({ queryKey: ["shifts-admin"] });
    },
    onError: () => notifications.show({ color: "red", message: "Failed to end shift." }),
  });

  const shifts   = data ?? [];
  const active   = shifts.filter((s) => s.is_active);
  const inactive = shifts.filter((s) => !s.is_active);

  return (
    <Stack gap="lg">
      <Group gap="xs">
        <ThemeIcon size={36} color="medsync" variant="light" radius="md">
          <IconClock size={20} />
        </ThemeIcon>
        <Box>
          <Title order={2}>Shift Management</Title>
          <Text size="xs" c="dimmed">
            {active.length} active shift{active.length !== 1 ? "s" : ""} · {shifts.length} total today
          </Text>
        </Box>
      </Group>

      {/* Active shifts */}
      <Card withBorder radius="md" p="lg" style={{ borderLeftWidth: 3, borderLeftColor: "var(--ok)" }}>
        <Text fw={700} mb="md" c="green">Active Shifts ({active.length})</Text>
        {isLoading ? (
          <Stack gap="xs">{[1,2,3].map((i) => <Skeleton key={i} height={48} />)}</Stack>
        ) : !active.length ? (
          <Text c="dimmed" size="sm">No active shifts.</Text>
        ) : (
          <Table.ScrollContainer minWidth={600}>
            <Table striped withTableBorder withColumnBorders>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Staff</Table.Th>
                  <Table.Th>Ward</Table.Th>
                  <Table.Th>Started</Table.Th>
                  <Table.Th>Duration</Table.Th>
                  <Table.Th>Action</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {active.map((s) => (
                  <Table.Tr key={s.id}>
                    <Table.Td><Text size="sm" fw={600}>{s.user_name}</Text></Table.Td>
                    <Table.Td><Text size="sm">{s.ward_name ?? "—"}</Text></Table.Td>
                    <Table.Td>
                      <Text size="sm">{dayjs(s.started_at).format("HH:mm")}</Text>
                      <Text size="xs" c="dimmed">{dayjs(s.started_at).format("DD MMM")}</Text>
                    </Table.Td>
                    <Table.Td>
                      <Badge color="green" variant="light">
                        {formatDuration(s.started_at)}
                      </Badge>
                    </Table.Td>
                    <Table.Td>
                      <Button
                        size="xs"
                        color="red"
                        variant="light"
                        leftSection={<IconPlayerStop size={14} />}
                        loading={endMutation.isPending}
                        onClick={() =>
                          modals.openConfirmModal({
                            title: "End shift?",
                            children: (
                              <>
                                <p style={{ margin: 0, fontSize: 14 }}>
                                  This will end <strong>{s.user_name}</strong>'s active shift
                                  (started {dayjs(s.started_at).format("HH:mm DD MMM")}).
                                  This action cannot be undone and affects attendance records.
                                </p>
                              </>
                            ),
                            labels: { confirm: "End shift", cancel: "Keep active" },
                            confirmProps: { color: "red" },
                            onConfirm: () => endMutation.mutate(s.id),
                          })
                        }
                      >
                        End shift
                      </Button>
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        )}
      </Card>

      {/* Completed shifts */}
      <Card withBorder radius="md" p="lg">
        <Text fw={700} mb="md" c="dimmed">Completed Shifts ({inactive.length})</Text>
        {isLoading ? (
          <Stack gap="xs">{[1,2,3].map((i) => <Skeleton key={i} height={48} />)}</Stack>
        ) : !inactive.length ? (
          <Text c="dimmed" size="sm">No completed shifts today.</Text>
        ) : (
          <Table.ScrollContainer minWidth={600}>
            <Table striped withTableBorder withColumnBorders>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Staff</Table.Th>
                  <Table.Th>Ward</Table.Th>
                  <Table.Th>Started</Table.Th>
                  <Table.Th>Ended</Table.Th>
                  <Table.Th>Duration</Table.Th>
                  <Table.Th>Break</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {inactive.map((s) => (
                  <Table.Tr key={s.id}>
                    <Table.Td><Text size="sm">{s.user_name}</Text></Table.Td>
                    <Table.Td><Text size="sm">{s.ward_name ?? "—"}</Text></Table.Td>
                    <Table.Td><Text size="sm">{dayjs(s.started_at).format("HH:mm DD MMM")}</Text></Table.Td>
                    <Table.Td>
                      <Text size="sm">{s.ended_at ? dayjs(s.ended_at).format("HH:mm DD MMM") : "—"}</Text>
                    </Table.Td>
                    <Table.Td>
                      <Badge color="blue" variant="light" size="sm">
                        {s.ended_at ? formatDuration(s.started_at, s.ended_at) : "—"}
                      </Badge>
                    </Table.Td>
                    <Table.Td>
                      <Text size="xs" c="dimmed">{s.break_minutes} min</Text>
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        )}
      </Card>
    </Stack>
  );
}
