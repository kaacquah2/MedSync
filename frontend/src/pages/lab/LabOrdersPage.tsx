import {
  Badge,
  Box,
  Button,
  Group,
  Indicator,
  SegmentedControl,
  Skeleton,
  Stack,
  Table,
  Text,
  ThemeIcon,
  Title,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconFlask } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import dayjs from "dayjs";
import relativeTime from "dayjs/plugin/relativeTime";
import { useState } from "react";
import { Link } from "react-router-dom";
import { fetchLabWorklist, updateLabOrderStatus } from "@/api/endpoints";
import { useAuth } from "@/auth/AuthProvider";
import type { LabOrder } from "@/types";

dayjs.extend(relativeTime);

const PRIORITY_COLORS = { routine: "blue", urgent: "orange", stat: "red" } as const;
const STATUS_COLORS   = { pending: "gray", in_progress: "blue", resulted: "green", cancelled: "red" } as const;

export function LabOrdersPage() {
  const { user } = useAuth();
  const qc = useQueryClient();
  const [filter, setFilter] = useState("pending");

  const { data, isLoading } = useQuery({
    queryKey: ["lab-worklist"],
    queryFn: () => fetchLabWorklist().then((r) => r.data),
    refetchInterval: 30_000,
  });

  const statusMutation = useMutation({
    mutationFn: ({ id, status }: { id: number; status: LabOrder["status"] }) =>
      updateLabOrderStatus(id, status),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["lab-worklist"] });
      notifications.show({ color: "green", message: "Order status updated." });
    },
    onError: () => notifications.show({ color: "red", message: "Update failed." }),
  });

  const isLabTech = user?.role === "lab_technician";

  const filtered = data?.filter((o) => {
    if (filter === "pending") return o.status === "pending";
    if (filter === "in_progress") return o.status === "in_progress";
    return true; // "all"
  }) ?? [];

  const statCount = data?.filter((o) => o.priority === "stat" && o.status === "pending").length ?? 0;

  return (
    <Stack gap="lg">
      <Group justify="space-between">
        <Group gap="xs">
          <ThemeIcon size={36} color="medsync" variant="light" radius="md">
            <IconFlask size={20} />
          </ThemeIcon>
          <Box>
            <Group gap="xs">
              <Title order={2}>Lab Order Worklist</Title>
              {statCount > 0 && (
                <Badge color="red" size="sm" variant="filled">
                  {statCount} STAT
                </Badge>
              )}
            </Group>
          </Box>
        </Group>
      </Group>

      <SegmentedControl
        value={filter}
        onChange={setFilter}
        data={[
          { label: "Pending", value: "pending" },
          { label: "In Progress", value: "in_progress" },
          { label: "All", value: "all" },
        ]}
        size="sm"
        maw={300}
      />

      {isLoading ? (
        <Stack gap="xs">
          {[1, 2, 3, 4].map((i) => <Skeleton key={i} height={52} radius="sm" />)}
        </Stack>
      ) : !filtered.length ? (
        <Box ta="center" py="xl">
          <Text c="dimmed" size="sm">No {filter === "all" ? "" : filter} orders found.</Text>
        </Box>
      ) : (
        <Table.ScrollContainer minWidth={700}>
        <Table striped highlightOnHover withTableBorder withColumnBorders>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Priority</Table.Th>
              <Table.Th>Test</Table.Th>
              <Table.Th>Patient</Table.Th>
              <Table.Th>Ordered By</Table.Th>
              <Table.Th>Ordered</Table.Th>
              <Table.Th>Status</Table.Th>
              {isLabTech && <Table.Th>Action</Table.Th>}
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {filtered.map((order) => (
              <Table.Tr key={order.id}>
                <Table.Td>
                  <Group gap="xs">
                    {order.priority === "stat" && (
                      <Indicator color="red" processing size={8} offset={4}>
                        <Box />
                      </Indicator>
                    )}
                    <Badge
                      color={PRIORITY_COLORS[order.priority] ?? "gray"}
                      size="sm"
                      variant={order.priority === "stat" ? "filled" : "light"}
                    >
                      {order.priority_display}
                    </Badge>
                  </Group>
                </Table.Td>
                <Table.Td>
                  <Text size="sm" fw={500}>{order.test_name}</Text>
                  {order.loinc_code && (
                    <Text size="xs" c="dimmed" ff="monospace">{order.loinc_code}</Text>
                  )}
                </Table.Td>
                <Table.Td>
                  <Text
                    component={Link}
                    to={`/patients/${order.patient_nhid}`}
                    size="sm"
                    c="blue"
                    ff="monospace"
                  >
                    {order.patient_nhid}
                  </Text>
                </Table.Td>
                <Table.Td>
                  <Text size="sm">{order.ordered_by_name ?? "—"}</Text>
                </Table.Td>
                <Table.Td>
                  <Text size="sm">{dayjs(order.created_at).fromNow()}</Text>
                </Table.Td>
                <Table.Td>
                  <Badge color={STATUS_COLORS[order.status] ?? "gray"} variant="light" size="sm">
                    {order.status_display}
                  </Badge>
                </Table.Td>
                {isLabTech && (
                  <Table.Td>
                    {order.status === "pending" && (
                      <Button
                        size="xs"
                        variant="light"
                        onClick={() => statusMutation.mutate({ id: order.id, status: "in_progress" })}
                        loading={statusMutation.isPending}
                      >
                        Start
                      </Button>
                    )}
                    {order.status === "in_progress" && (
                      <Button
                        size="xs"
                        color="green"
                        variant="light"
                        onClick={() => statusMutation.mutate({ id: order.id, status: "resulted" })}
                        loading={statusMutation.isPending}
                      >
                        Mark Resulted
                      </Button>
                    )}
                  </Table.Td>
                )}
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
        </Table.ScrollContainer>
      )}
    </Stack>
  );
}
