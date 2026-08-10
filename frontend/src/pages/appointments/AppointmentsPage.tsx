import {
  Badge,
  Box,
  Button,
  Group,
  Menu,
  SegmentedControl,
  Skeleton,
  Stack,
  Table,
  Text,
  ThemeIcon,
  Title,
} from "@mantine/core";
import {
  IconCalendar,
  IconCheck,
  IconChevronDown,
  IconUserX,
  IconX,
} from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import dayjs from "dayjs";
import { useState } from "react";
import { appointmentAction, fetchAppointments } from "@/api/endpoints";
import { useAuth } from "@/auth/AuthProvider";
import { notifications } from "@mantine/notifications";
import type { Appointment } from "@/types";

const STATUS_COLORS: Record<Appointment["status"], string> = {
  scheduled:   "blue",
  checked_in:  "teal",
  in_progress: "indigo",
  completed:   "green",
  no_show:     "orange",
  cancelled:   "red",
};

function AppointmentStatusBadge({ appt }: { appt: Appointment }) {
  return (
    <Badge color={STATUS_COLORS[appt.status]} variant="light" size="sm">
      {appt.status_display}
    </Badge>
  );
}

export function AppointmentsPage() {
  const { user } = useAuth();
  const qc = useQueryClient();
  const [dateFilter, setDateFilter] = useState("today");
  const [statusFilter, setStatusFilter] = useState("");

  const today = dayjs().format("YYYY-MM-DD");
  const params: Record<string, string> = {};
  if (dateFilter === "today") params.date = today;
  if (statusFilter) params.status = statusFilter;

  const { data, isLoading } = useQuery({
    queryKey: ["appointments", dateFilter, statusFilter],
    queryFn: () => fetchAppointments(params).then((r) => r.data),
    refetchInterval: 30_000,
  });

  const actionMutation = useMutation({
    mutationFn: ({ id, action }: { id: number; action: string }) =>
      appointmentAction(id, action),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["appointments"] });
      notifications.show({ color: "green", message: "Appointment updated." });
    },
    onError: () => {
      notifications.show({ color: "red", message: "Action failed." });
    },
  });

  const isReceptionist = user?.role === "receptionist";

  return (
    <Stack gap="lg">
      <Group justify="space-between">
        <Group gap="xs">
          <ThemeIcon size={36} color="medsync" variant="light" radius="md">
            <IconCalendar size={20} />
          </ThemeIcon>
          <Title order={2}>Appointments</Title>
        </Group>
      </Group>

      {/* Filters */}
      <Group gap="md" wrap="wrap">
        <SegmentedControl
          value={dateFilter}
          onChange={setDateFilter}
          data={[
            { label: "Today", value: "today" },
            { label: "All", value: "all" },
          ]}
          size="sm"
          maw={160}
        />
        <SegmentedControl
          value={statusFilter}
          onChange={setStatusFilter}
          data={[
            { label: "All Status", value: "" },
            { label: "Scheduled", value: "scheduled" },
            { label: "Checked In", value: "checked_in" },
            { label: "Completed", value: "completed" },
          ]}
          size="sm"
        />
      </Group>

      {isLoading ? (
        <Stack gap="xs">
          {[1, 2, 3, 4, 5].map((i) => <Skeleton key={i} height={52} radius="sm" />)}
        </Stack>
      ) : !data?.length ? (
        <Box ta="center" py="xl">
          <Text c="dimmed" size="sm">
            No appointments {dateFilter === "today" ? "today" : "found"}.
          </Text>
        </Box>
      ) : (
        <Table.ScrollContainer minWidth={700}>
        <Table striped highlightOnHover withTableBorder withColumnBorders>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Time</Table.Th>
              <Table.Th>Patient</Table.Th>
              <Table.Th>Provider</Table.Th>
              <Table.Th>Type</Table.Th>
              <Table.Th>Reason</Table.Th>
              <Table.Th>Status</Table.Th>
              {isReceptionist && <Table.Th>Actions</Table.Th>}
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {data.map((appt) => (
              <Table.Tr key={appt.id}>
                <Table.Td>
                  <Text size="sm" fw={600}>{dayjs(appt.scheduled_for).format("HH:mm")}</Text>
                  <Text size="xs" c="dimmed">{dayjs(appt.scheduled_for).format("DD MMM")}</Text>
                </Table.Td>
                <Table.Td>
                  <Text size="sm" fw={500}>{appt.patient_name}</Text>
                  <Text size="xs" c="dimmed" ff="monospace">{appt.patient_nhid}</Text>
                </Table.Td>
                <Table.Td>
                  <Text size="sm">{appt.provider_name ?? "Unassigned"}</Text>
                </Table.Td>
                <Table.Td>
                  <Badge variant="outline" size="xs">{appt.appointment_type_display}</Badge>
                </Table.Td>
                <Table.Td>
                  <Text size="sm" lineClamp={1}>{appt.reason || "—"}</Text>
                </Table.Td>
                <Table.Td>
                  <AppointmentStatusBadge appt={appt} />
                </Table.Td>
                {isReceptionist && (
                  <Table.Td>
                    <Menu shadow="sm" width={160}>
                      <Menu.Target>
                        <Button
                          size="xs"
                          variant="light"
                          rightSection={<IconChevronDown size={12} />}
                          disabled={["completed", "cancelled"].includes(appt.status)}
                        >
                          Action
                        </Button>
                      </Menu.Target>
                      <Menu.Dropdown>
                        {appt.status === "scheduled" && (
                          <Menu.Item
                            leftSection={<IconCheck size={14} />}
                            onClick={() => actionMutation.mutate({ id: appt.id, action: "check_in" })}
                          >
                            Check In
                          </Menu.Item>
                        )}
                        {appt.status === "scheduled" && (
                          <Menu.Item
                            leftSection={<IconUserX size={14} />}
                            color="orange"
                            onClick={() => actionMutation.mutate({ id: appt.id, action: "no_show" })}
                          >
                            No Show
                          </Menu.Item>
                        )}
                        {appt.status === "checked_in" && (
                          <Menu.Item
                            leftSection={<IconCheck size={14} />}
                            onClick={() => actionMutation.mutate({ id: appt.id, action: "start" })}
                          >
                            Start
                          </Menu.Item>
                        )}
                        {appt.status === "in_progress" && (
                          <Menu.Item
                            leftSection={<IconCheck size={14} />}
                            color="green"
                            onClick={() => actionMutation.mutate({ id: appt.id, action: "complete" })}
                          >
                            Complete
                          </Menu.Item>
                        )}
                        <Menu.Divider />
                        <Menu.Item
                          leftSection={<IconX size={14} />}
                          color="red"
                          onClick={() => actionMutation.mutate({ id: appt.id, action: "cancel" })}
                        >
                          Cancel
                        </Menu.Item>
                      </Menu.Dropdown>
                    </Menu>
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
