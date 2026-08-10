import {
  Card,
  Group,
  ScrollArea,
  Table,
  Text,
  ThemeIcon,
  Title,
  TextInput,
  Select,
  Badge,
  Stack,
  Box,
  Skeleton,
} from "@mantine/core";
import { IconClock, IconSearch } from "@tabler/icons-react";
import { useState, useMemo } from "react";
import dayjs from "dayjs";
import duration from "dayjs/plugin/duration";
import { useQuery } from "@tanstack/react-query";
import { fetchShifts } from "@/api/endpoints";

dayjs.extend(duration);

export function AttendanceLogPage() {
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<string | null>(null);

  const { data: shifts, isLoading } = useQuery({
    queryKey: ["shifts-attendance"],
    queryFn: () => fetchShifts().then((r) => r.data),
  });

  const filtered = useMemo(() => {
    return (shifts || []).filter((s) => {
      const matchSearch =
        s.user_name.toLowerCase().includes(search.toLowerCase()) ||
        (s.ward_name || "").toLowerCase().includes(search.toLowerCase());
      const isActive = s.is_active;
      const statusVal = isActive ? "active" : "completed";
      const matchStatus = !statusFilter || statusFilter === statusVal;
      return matchSearch && matchStatus;
    });
  }, [shifts, search, statusFilter]);

  return (
    <Stack gap="lg">
      {/* Header */}
      <Group gap="xs">
        <ThemeIcon size={36} color="medsync" variant="light" radius="md">
          <IconClock size={20} />
        </ThemeIcon>
        <Box>
          <Title order={2} style={{ fontSize: "20px", fontWeight: 500 }}>Attendance Log</Title>
          <Text size="xs" c="dimmed">Staff shift records and attendance</Text>
        </Box>
      </Group>

      {/* Filter Bar */}
      <Card withBorder radius="md" p="md" bg="var(--surface-2)">
        <Group gap="md" grow>
          <TextInput
            placeholder="Search by name or ward…"
            leftSection={<IconSearch size={16} />}
            value={search}
            onChange={(e) => setSearch(e.currentTarget.value)}
          />
          <Select
            placeholder="Shift status"
            data={[
              { value: "active", label: "Active shift" },
              { value: "completed", label: "Completed" },
            ]}
            value={statusFilter}
            onChange={setStatusFilter}
            clearable
          />
        </Group>
      </Card>

      {/* Log Table */}
      <Card withBorder radius="md" p="lg" bg="var(--surface-2)">
        {isLoading ? (
          <Stack gap="xs">
            {[1, 2, 3, 4, 5].map((i) => <Skeleton key={i} height={36} radius="sm" />)}
          </Stack>
        ) : (
          <ScrollArea>
            <Table striped highlightOnHover>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Staff</Table.Th>
                  <Table.Th>Ward</Table.Th>
                  <Table.Th>Started</Table.Th>
                  <Table.Th>Ended</Table.Th>
                  <Table.Th>Duration</Table.Th>
                  <Table.Th>Status</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {filtered.map((s) => {
                  const started = dayjs(s.started_at);
                  const ended = s.ended_at ? dayjs(s.ended_at) : null;
                  const durationMins = ended
                    ? ended.diff(started, "minute") - (s.break_minutes || 0)
                    : dayjs().diff(started, "minute") - (s.break_minutes || 0);
                  const durationStr = durationMins >= 60
                    ? `${Math.floor(durationMins / 60)}h ${durationMins % 60}m`
                    : `${durationMins}m`;

                  return (
                    <Table.Tr key={s.id}>
                      <Table.Td fw={600}>{s.user_name}</Table.Td>
                      <Table.Td>{s.ward_name || "—"}</Table.Td>
                      <Table.Td>{started.format("DD MMM YYYY HH:mm")}</Table.Td>
                      <Table.Td>{ended ? ended.format("HH:mm") : "—"}</Table.Td>
                      <Table.Td>{durationStr}</Table.Td>
                      <Table.Td>
                        <Badge color={s.is_active ? "green" : "gray"} variant="light">
                          {s.is_active ? "Active" : "Completed"}
                        </Badge>
                      </Table.Td>
                    </Table.Tr>
                  );
                })}
                {filtered.length === 0 && (
                  <Table.Tr>
                    <Table.Td colSpan={6} style={{ textAlign: "center" }} c="dimmed">
                      No attendance records found.
                    </Table.Td>
                  </Table.Tr>
                )}
              </Table.Tbody>
            </Table>
          </ScrollArea>
        )}
      </Card>
    </Stack>
  );
}
