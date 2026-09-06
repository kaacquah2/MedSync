/**
 * BreakGlassReviewPage — super admin reviews emergency access events.
 * Sourced from live audit log filtered to BREAK_GLASS action.
 * Reviewed state is persisted to localStorage so it survives page refreshes.
 */

import {
  Badge,
  Box,
  Button,
  Card,
  Group,
  Select,
  Skeleton,
  Stack,
  Table,
  Text,
  ThemeIcon,
  Title,
} from "@mantine/core";
import { IconCheck, IconEye, IconShieldLock } from "@tabler/icons-react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import dayjs from "dayjs";
import { useState } from "react";
import { Link } from "react-router-dom";
import { fetchAuditLog, reviewAuditLog, unreviewAuditLog } from "@/api/endpoints";

export function BreakGlassReviewPage() {
  const queryClient = useQueryClient();
  const [hospitalFilter, setHosp]    = useState<string | null>(null);
  const [dateFilter, setDate]        = useState<string | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["audit-break-glass"],
    queryFn: () => fetchAuditLog({ action: "BREAK_GLASS", page_size: "100" }).then((r) => r.data),
  });

  const entries = data?.results ?? [];

  const reviewMutation = useMutation({
    mutationFn: (id: number) => reviewAuditLog(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["audit-break-glass"] });
    },
  });

  const unreviewMutation = useMutation({
    mutationFn: (id: number) => unreviewAuditLog(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["audit-break-glass"] });
    },
  });

  const hospitalOptions = Array.from(
    new Set(entries.map((e) => e.actor_hospital).filter(Boolean))
  ).map((h) => ({ value: h, label: h }));

  const dateOptions = [
    { value: "today", label: "Today" },
    { value: "7d",    label: "Last 7 days" },
    { value: "30d",   label: "Last 30 days" },
    { value: "all",   label: "All time" },
  ];

  const filtered = entries.filter((e) => {
    if (hospitalFilter && e.actor_hospital !== hospitalFilter) return false;
    if (dateFilter && dateFilter !== "all") {
      const ts = dayjs(e.timestamp);
      if (dateFilter === "today" && !ts.isSame(dayjs(), "day")) return false;
      if (dateFilter === "7d"  && dayjs().diff(ts, "day") > 7)  return false;
      if (dateFilter === "30d" && dayjs().diff(ts, "day") > 30) return false;
    }
    return true;
  });

  const pendingReview = filtered.filter((e) => !e.is_reviewed).length;
  const reviewedCount = filtered.filter((e) => e.is_reviewed).length;

  function markReviewed(id: number) {
    reviewMutation.mutate(id);
  }

  function markAllReviewed() {
    const pending = filtered.filter((e) => !e.is_reviewed);
    Promise.all(pending.map((e) => reviewAuditLog(e.id))).then(() => {
      queryClient.invalidateQueries({ queryKey: ["audit-break-glass"] });
    });
  }

  return (
    <Stack gap="lg">
      <Group justify="space-between">
        <Group gap="xs">
          <ThemeIcon size={36} color="red" variant="light" radius="md">
            <IconShieldLock size={20} />
          </ThemeIcon>
          <Box>
            <Title order={2}>Break-Glass Review</Title>
            <Text size="xs" c="dimmed">Emergency access events requiring supervisory review</Text>
          </Box>
        </Group>
        {pendingReview > 0 && (
          <Button color="orange" variant="light" size="sm" leftSection={<IconCheck size={16} />} onClick={markAllReviewed}>
            Mark all as reviewed ({pendingReview})
          </Button>
        )}
      </Group>

      {/* Filters */}
      <Group gap="sm" wrap="wrap">
        <Select
          placeholder="Filter by hospital"
          data={hospitalOptions}
          value={hospitalFilter}
          onChange={setHosp}
          clearable
          maw={220}
          size="sm"
        />
        <Select
          placeholder="Date range"
          data={dateOptions}
          value={dateFilter}
          onChange={setDate}
          clearable
          maw={160}
          size="sm"
        />
        {(hospitalFilter || dateFilter) && (
          <Button variant="subtle" size="sm" onClick={() => { setHosp(null); setDate(null); }}>
            Clear filters
          </Button>
        )}
      </Group>

      {/* Summary cards */}
      <Group gap="md">
        {[
          { label: "Total events",     value: entries.length,            color: "blue" },
          { label: "Pending review",   value: pendingReview,             color: "orange" },
          { label: "Reviewed",         value: reviewedCount,             color: "green" },
        ].map((c) => (
          <Card key={c.label} withBorder radius="md" p="md" miw={150}>
            <Text size="xs" c="dimmed" tt="uppercase" fw={700}>{c.label}</Text>
            <Text size="xl" fw={800} c={c.color}>{c.value}</Text>
          </Card>
        ))}
      </Group>

      {isLoading ? (
        <Stack gap="xs">{[1,2,3,4,5].map((i) => <Skeleton key={i} height={52} radius="sm" />)}</Stack>
      ) : !filtered.length ? (
        <Box ta="center" py="xl">
          <Text c="dimmed" size="sm">No break-glass events found.</Text>
        </Box>
      ) : (
        <Card withBorder radius="md" p={0}>
          <Table.ScrollContainer minWidth={800}>
            <Table striped highlightOnHover withTableBorder withColumnBorders>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>User</Table.Th>
                  <Table.Th>Hospital</Table.Th>
                  <Table.Th>Patient</Table.Th>
                  <Table.Th>Reason</Table.Th>
                  <Table.Th>Timestamp</Table.Th>
                  <Table.Th>Status</Table.Th>
                  <Table.Th>Action</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {filtered.map((e) => {
                  const isRev = !!e.is_reviewed;
                  return (
                    <Table.Tr key={e.id} bg={isRev ? undefined : "var(--bg-red)"}>
                      <Table.Td>
                        <Text size="sm" fw={600}>{e.actor_username}</Text>
                        <Text size="xs" c="dimmed">{e.actor_role}</Text>
                      </Table.Td>
                      <Table.Td><Text size="sm">{e.actor_hospital}</Text></Table.Td>
                      <Table.Td>
                        {e.patient_nhid ? (
                          <Text component={Link} to={`/patients/${e.patient_nhid}`} size="sm" c="blue" ff="monospace">
                            {e.patient_nhid}
                          </Text>
                        ) : "—"}
                      </Table.Td>
                      <Table.Td>
                        <Text size="sm" style={{ maxWidth: 200 }} lineClamp={2}>
                          {(e.extra?.reason as string) ?? "—"}
                        </Text>
                      </Table.Td>
                      <Table.Td>
                        <Text size="sm">{dayjs(e.timestamp).format("DD MMM YYYY HH:mm")}</Text>
                        <Text size="xs" c="dimmed">{dayjs(e.timestamp).fromNow()}</Text>
                      </Table.Td>
                      <Table.Td>
                        <Badge
                          color={isRev ? "green" : "orange"}
                          variant={isRev ? "light" : "filled"}
                          size="sm"
                        >
                          {isRev ? "Reviewed" : "Pending"}
                        </Badge>
                      </Table.Td>
                      <Table.Td>
                        {!isRev ? (
                          <Button
                            size="xs"
                            variant="light"
                            color="green"
                            leftSection={<IconCheck size={14} />}
                            loading={reviewMutation.isPending && reviewMutation.variables === e.id}
                            onClick={() => markReviewed(e.id)}
                          >
                            Mark reviewed
                          </Button>
                        ) : (
                          <Button
                            size="xs"
                            variant="subtle"
                            leftSection={<IconEye size={14} />}
                            loading={unreviewMutation.isPending && unreviewMutation.variables === e.id}
                            onClick={() => unreviewMutation.mutate(e.id)}
                          >
                            Undo
                          </Button>
                        )}
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
