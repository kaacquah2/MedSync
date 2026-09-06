/**
 * Super-Admin Audit Logs — full log with filters and chain validator.
 */

import {
  Anchor,
  Badge,
  Box,
  Button,
  Card,
  Group,
  Modal,
  Pagination,
  ScrollArea,
  Select,
  Skeleton,
  Stack,
  Table,
  Text,
  TextInput,
  ThemeIcon,
  Title,
} from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import {
  IconCheck,
  IconSearch,
  IconShieldCheck,
  IconShieldOff,
  IconX,
} from "@tabler/icons-react";
import { useMutation, useQuery } from "@tanstack/react-query";
import dayjs from "dayjs";
import relativeTime from "dayjs/plugin/relativeTime";
import { useState } from "react";
import { Link } from "react-router-dom";
import { fetchAuditActions, fetchAuditLog, validateAuditChain } from "@/api/endpoints";

dayjs.extend(relativeTime);

export function AuditLogsPage() {
  const [page, setPage]   = useState(1);
  const [nhid, setNhid]   = useState("");
  const [actor, setActor] = useState("");
  const [action, setAction] = useState("");
  const [chainOpen, { open: openChain, close: closeChain }] = useDisclosure(false);

  const params: Record<string, string> = { page: String(page) };
  if (nhid)   params.nhid   = nhid;
  if (actor)  params.actor  = actor;
  if (action) params.action = action;

  const { data, isLoading } = useQuery({
    queryKey: ["audit-log", page, nhid, actor, action],
    queryFn: () => fetchAuditLog(params).then((r) => r.data),
    staleTime: 30_000,
  });

  const { data: actionChoices } = useQuery({
    queryKey: ["audit-actions"],
    queryFn: () => fetchAuditActions().then((r) => r.data),
    staleTime: 5 * 60 * 1000,
  });

  const chainMutation = useMutation({
    mutationFn: validateAuditChain,
    onSuccess: () => openChain(),
    onError:   () => notifications.show({ color: "red", message: "Chain validation failed." }),
  });

  return (
    <Stack gap="lg">
      <Group justify="space-between">
        <Group gap="sm">
          <ThemeIcon size={36} color="medsync" variant="light" radius="md">
            <IconShieldCheck size={20} />
          </ThemeIcon>
          <Title order={2}>Audit Log</Title>
        </Group>
        <Button
          leftSection={<IconShieldCheck size={16} />}
          variant="light"
          color="medsync"
          onClick={() => chainMutation.mutate()}
          loading={chainMutation.isPending}
        >
          Validate Chain
        </Button>
      </Group>

      {/* Filters */}
      <Group gap="sm">
        <TextInput
          placeholder="Patient NHID…"
          leftSection={<IconSearch size={14} />}
          value={nhid}
          onChange={(e) => { setNhid(e.currentTarget.value); setPage(1); }}
          size="sm"
          maw={200}
        />
        <TextInput
          placeholder="Actor username…"
          value={actor}
          onChange={(e) => { setActor(e.currentTarget.value); setPage(1); }}
          size="sm"
          maw={180}
        />
        <Select
          placeholder="All actions"
          value={action || null}
          onChange={(v) => { setAction(v ?? ""); setPage(1); }}
          data={actionChoices?.map((c) => ({ value: c.value, label: c.label })) ?? []}
          clearable
          searchable
          size="sm"
          maw={220}
        />
        {(nhid || actor || action) && (
          <Button
            size="sm"
            variant="subtle"
            onClick={() => { setNhid(""); setActor(""); setAction(""); setPage(1); }}
          >
            Clear
          </Button>
        )}
      </Group>

      {isLoading ? (
        <Stack gap="xs">
          {[1, 2, 3, 4].map((i) => <Skeleton key={i} height={52} radius="sm" />)}
        </Stack>
      ) : (
        <ScrollArea>
          <Table striped withTableBorder withColumnBorders>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Actor</Table.Th>
                <Table.Th>Action</Table.Th>
                <Table.Th>Patient</Table.Th>
                <Table.Th>Target</Table.Th>
                <Table.Th>Cross-Hospital</Table.Th>
                <Table.Th>IP</Table.Th>
                <Table.Th>Time</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {(data?.results ?? []).map((entry) => (
                <Table.Tr
                  key={entry.id}
                  bg={entry.is_cross_hospital ? "var(--bg-amber)" : undefined}
                >
                  <Table.Td>
                    <Text size="sm" fw={600}>{entry.actor_username}</Text>
                    <Text size="xs" c="dimmed">{entry.actor_role} · {entry.actor_hospital || "N/A"}</Text>
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
                    <Text size="xs">{entry.target_type || "—"}</Text>
                  </Table.Td>
                  <Table.Td>
                    {entry.is_cross_hospital ? (
                      <Badge color="yellow" size="xs">YES</Badge>
                    ) : "—"}
                  </Table.Td>
                  <Table.Td>
                    <Text size="xs" ff="monospace">{entry.ip_address ?? "—"}</Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="xs">{dayjs(entry.timestamp).fromNow()}</Text>
                  </Table.Td>
                </Table.Tr>
              ))}
              {!data?.results?.length && (
                <Table.Tr>
                  <Table.Td colSpan={7}>
                    <Text ta="center" c="dimmed" size="sm" py="md">
                      No audit entries match the current filters.
                    </Text>
                  </Table.Td>
                </Table.Tr>
              )}
            </Table.Tbody>
          </Table>
        </ScrollArea>
      )}

      {data && (
        <Group justify="space-between" align="center">
          <Text size="xs" c="dimmed">
            Showing {data.results.length} of {data.count} entries (page {page} of {Math.ceil(data.count / 50) || 1})
          </Text>
          {Math.ceil(data.count / 50) > 1 && (
            <Pagination
              total={Math.ceil(data.count / 50)}
              value={page}
              onChange={setPage}
              size="sm"
            />
          )}
        </Group>
      )}

      {/* Chain validation modal */}
      <Modal
        opened={chainOpen}
        onClose={closeChain}
        title="Audit Chain Validation"
        size="xl"
      >
        {chainMutation.data?.data && (
          <ChainReport data={chainMutation.data.data} />
        )}
      </Modal>
    </Stack>
  );
}

function ChainReport({ data }: { data: import("@/types").ChainValidation }) {
  return (
    <Stack gap="md">
      <Card
        withBorder
        p="md"
        radius="md"
        bg={data.chain_valid ? "var(--bg-green)" : "var(--bg-red)"}
      >
        <Group gap="sm">
          <ThemeIcon
            size={40}
            color={data.chain_valid ? "green" : "red"}
            variant="light"
            radius="xl"
          >
            {data.chain_valid ? <IconShieldCheck size={24} /> : <IconShieldOff size={24} />}
          </ThemeIcon>
          <Box>
            <Text fw={700} size="lg" c={data.chain_valid ? "green" : "red"}>
              {data.chain_valid ? "Chain Valid" : "Chain Compromised"}
            </Text>
            <Text size="sm" c="dimmed">
              {data.total_entries} entries verified
            </Text>
          </Box>
        </Group>
      </Card>

      <ScrollArea mah={400}>
        <Stack gap={4}>
          {data.nodes.map((node) => (
            <Group key={node.id} gap="sm" p="xs" style={{
              borderRadius: 6,
              background: node.valid ? "transparent" : "var(--mantine-color-red-0)",
            }}>
              <ThemeIcon size={20} color={node.valid ? "green" : "red"} variant="light" radius="xl">
                {node.valid ? <IconCheck size={12} /> : <IconX size={12} />}
              </ThemeIcon>
              <Text size="xs" ff="monospace" c="dimmed" style={{ flex: 1 }}>
                #{node.id} · {node.action} · {node.actor} · {dayjs(node.timestamp).format("DD MMM HH:mm")}
              </Text>
              <Text size="xs" ff="monospace" c="dimmed">
                {node.row_hash}
              </Text>
            </Group>
          ))}
        </Stack>
      </ScrollArea>
    </Stack>
  );
}
