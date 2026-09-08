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
  Textarea,
  ThemeIcon,
  Title,
} from "@mantine/core";
import { modals } from "@mantine/modals";
import { notifications } from "@mantine/notifications";
import { IconArrowLeftRight, IconChevronDown, IconCheck, IconX } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import dayjs from "dayjs";
import relativeTime from "dayjs/plugin/relativeTime";
import { useState } from "react";
import { Link } from "react-router-dom";
import { fetchReferrals, updateReferralStatus } from "@/api/endpoints";
import { useAuth } from "@/auth/AuthProvider";
import type { Referral } from "@/types";

dayjs.extend(relativeTime);

const STATUS_COLORS: Record<string, string> = {
  draft:     "gray",
  sent:      "blue",
  accepted:  "teal",
  rejected:  "red",
  completed: "green",
  cancelled: "red",
};

const PRIORITY_COLORS: Record<string, string> = { routine: "blue", urgent: "orange", stat: "red" };

export function ReferralsPage() {
  const { user } = useAuth();
  const qc = useQueryClient();
  const [direction, setDirection] = useState("all");

  const params: Record<string, string> = {};
  if (direction !== "all") params.direction = direction;

  const { data, isLoading } = useQuery({
    queryKey: ["referrals", direction],
    queryFn: () => fetchReferrals(params).then((r) => r.data.results ?? []),
  });

  const statusMutation = useMutation({
    mutationFn: ({ id, status, notes }: { id: number; status: string; notes?: string }) =>
      updateReferralStatus(id, status, notes),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["referrals"] });
      notifications.show({ color: "green", message: "Referral updated." });
    },
    onError: () => notifications.show({ color: "red", message: "Update failed." }),
  });

  function openStatusConfirm(ref: Referral, newStatus: "accepted" | "rejected" | "completed") {
    const isReject = newStatus === "rejected";
    const notesRef = { current: "" };
    modals.openConfirmModal({
      title: isReject ? "Reject referral?" : newStatus === "accepted" ? "Accept referral?" : "Mark as completed?",
      children: (
        <Stack gap="sm">
          <Text size="sm">
            {isReject
              ? `Rejecting the referral for patient ${ref.patient_name} from ${ref.from_hospital_name}.`
              : newStatus === "accepted"
              ? `Accepting referral for patient ${ref.patient_name} from ${ref.from_hospital_name}.`
              : `Marking referral for ${ref.patient_name} as completed.`}
          </Text>
          <Textarea
            label={isReject ? "Reason for rejection (required)" : "Notes (optional)"}
            placeholder={isReject ? "Explain why this referral is being rejected…" : "Add any handover notes…"}
            minRows={3}
            required={isReject}
            onChange={(e) => { notesRef.current = e.currentTarget.value; }}
          />
        </Stack>
      ),
      labels: {
        confirm: isReject ? "Reject referral" : newStatus === "accepted" ? "Accept referral" : "Mark completed",
        cancel: "Cancel",
      },
      confirmProps: { color: isReject ? "red" : "teal" },
      onConfirm: () => {
        if (isReject && notesRef.current.trim().length < 10) {
          notifications.show({ color: "red", message: "Rejection reason must be at least 10 characters." });
          return;
        }
        statusMutation.mutate({ id: ref.id, status: newStatus, notes: notesRef.current.trim() || undefined });
      },
    });
  }

  const canManage = user?.role === "doctor";

  return (
    <Stack gap="lg">
      <Group justify="space-between">
        <Group gap="xs">
          <ThemeIcon size={36} color="medsync" variant="light" radius="md">
            <IconArrowLeftRight size={20} />
          </ThemeIcon>
          <Title order={2}>Referrals</Title>
        </Group>
      </Group>

      <SegmentedControl
        value={direction}
        onChange={setDirection}
        data={[
          { label: "All", value: "all" },
          { label: "Outgoing", value: "outgoing" },
          { label: "Incoming", value: "incoming" },
        ]}
        size="sm"
        maw={300}
      />

      {isLoading ? (
        <Stack gap="xs">
          {[1, 2, 3].map((i) => <Skeleton key={i} height={52} radius="sm" />)}
        </Stack>
      ) : !data?.length ? (
        <Box ta="center" py="xl">
          <Text c="dimmed" size="sm">No referrals found.</Text>
        </Box>
      ) : (
        <Table.ScrollContainer minWidth={800}>
        <Table striped highlightOnHover withTableBorder withColumnBorders>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Priority</Table.Th>
              <Table.Th>Patient</Table.Th>
              <Table.Th>From → To</Table.Th>
              <Table.Th>Provider</Table.Th>
              <Table.Th>Reason</Table.Th>
              <Table.Th>Status</Table.Th>
              <Table.Th>Created</Table.Th>
              {canManage && <Table.Th>Actions</Table.Th>}
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {(data ?? []).map((ref: Referral) => (
              <Table.Tr key={ref.id}>
                <Table.Td>
                  <Badge
                    color={PRIORITY_COLORS[ref.priority] ?? "blue"}
                    size="sm"
                    variant={ref.priority === "stat" ? "filled" : "light"}
                  >
                    {ref.priority_display}
                  </Badge>
                </Table.Td>
                <Table.Td>
                  <Text
                    component={Link}
                    to={`/patients/${ref.patient_nhid}`}
                    size="sm"
                    fw={500}
                    c="blue"
                  >
                    {ref.patient_name}
                  </Text>
                  <Text size="xs" c="dimmed" ff="monospace">{ref.patient_nhid}</Text>
                </Table.Td>
                <Table.Td>
                  <Group gap={4}>
                    <Badge size="xs" variant="outline">{ref.from_hospital_name}</Badge>
                    <IconArrowLeftRight size={12} />
                    <Badge size="xs" variant="outline">{ref.to_hospital_name}</Badge>
                  </Group>
                </Table.Td>
                <Table.Td>
                  <Text size="sm">{ref.from_provider_name ?? "—"}</Text>
                </Table.Td>
                <Table.Td>
                  <Text size="sm" lineClamp={2}>{ref.reason}</Text>
                </Table.Td>
                <Table.Td>
                  <Badge color={STATUS_COLORS[ref.status]} variant="light" size="sm">
                    {ref.status_display}
                  </Badge>
                </Table.Td>
                <Table.Td>
                  <Text size="xs" c="dimmed">{dayjs(ref.created_at).fromNow()}</Text>
                </Table.Td>
                {canManage && (
                  <Table.Td>
                    {ref.status === "sent" && (
                      <Menu shadow="sm" width={140}>
                        <Menu.Target>
                          <Button size="xs" variant="light" rightSection={<IconChevronDown size={12} />}>
                            Respond
                          </Button>
                        </Menu.Target>
                        <Menu.Dropdown>
                          <Menu.Item
                            leftSection={<IconCheck size={14} />}
                            color="teal"
                            onClick={() => openStatusConfirm(ref, "accepted")}
                          >
                            Accept
                          </Menu.Item>
                          <Menu.Item
                            leftSection={<IconX size={14} />}
                            color="red"
                            onClick={() => openStatusConfirm(ref, "rejected")}
                          >
                            Reject
                          </Menu.Item>
                        </Menu.Dropdown>
                      </Menu>
                    )}
                    {ref.status === "accepted" && (
                      <Button
                        size="xs"
                        color="green"
                        variant="light"
                        onClick={() => statusMutation.mutate({ id: ref.id, status: "completed" })}
                      >
                        Complete
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
