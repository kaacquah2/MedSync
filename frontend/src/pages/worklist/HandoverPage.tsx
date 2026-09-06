/**
 * HandoverPage — nurse shift handover with per-patient entries.
 * Outgoing nurse fills per-patient summary + tasks + concerns.
 * Incoming nurse acknowledges received handovers.
 */

import {
  Badge,
  Box,
  Button,
  Card,
  Divider,
  Group,
  Skeleton,
  Stack,
  Table,
  Text,
  Textarea,
  ThemeIcon,
  Title,
} from "@mantine/core";
import { useForm } from "@mantine/form";
import { notifications } from "@mantine/notifications";
import { IconArrowRight, IconCheck, IconClipboardList } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import dayjs from "dayjs";
import { acknowledgeHandover, createHandover, fetchHandovers, fetchWards } from "@/api/endpoints";

export function HandoverPage() {
  const qc = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ["handovers"],
    queryFn:  () => fetchHandovers().then((r) => r.data),
  });

  const { data: wards } = useQuery({
    queryKey: ["handover-wards"],
    queryFn:  () => fetchWards().then((r) => r.data),
  });

  // Build patient list from occupied beds
  const patients = (wards ?? [])
    .flatMap((w) => w.beds.filter((b) => b.patient_nhid).map((b) => ({ nhid: b.patient_nhid!, bed: b.label, ward: w.name })));

  const form = useForm({
    initialValues: {
      summary:       "",
      pending_tasks: "",
      concerns:      "",
      next_shift:    "",
    },
    validate: {
      summary: (v) => (v.trim().length >= 10 ? null : "Summary must be at least 10 characters."),
    },
  });

  const ackMutation = useMutation({
    mutationFn: (id: number) => acknowledgeHandover(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["handovers"] });
      notifications.show({ color: "green", message: "Handover acknowledged." });
    },
    onError: () => notifications.show({ color: "red", message: "Failed to acknowledge handover." }),
  });

  const ackAllMutation = useMutation({
    mutationFn: async (ids: number[]) => {
      for (const id of ids) await acknowledgeHandover(id);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["handovers"] });
      notifications.show({ color: "green", message: "All handovers acknowledged." });
    },
  });

  const mutation = useMutation({
    mutationFn: (values: typeof form.values) =>
      createHandover({
        summary: [
          `SUMMARY: ${values.summary}`,
          values.pending_tasks ? `PENDING: ${values.pending_tasks}` : "",
          values.concerns      ? `CONCERNS: ${values.concerns}` : "",
          values.next_shift    ? `FOR NEXT SHIFT: ${values.next_shift}` : "",
        ].filter(Boolean).join("\n\n"),
      }),
    onSuccess: () => {
      notifications.show({ color: "green", icon: <IconCheck />, message: "Handover submitted." });
      form.reset();
      qc.invalidateQueries({ queryKey: ["handovers"] });
    },
    onError: () => notifications.show({ color: "red", message: "Failed to submit handover." }),
  });

  const pendingHandovers = (data ?? []).filter((h) => !h.acknowledged_at);

  return (
    <Stack gap="lg">
      <Group justify="space-between" align="center" className="no-print">
        <Group gap="xs">
          <ThemeIcon size={36} color="medsync" variant="light" radius="md">
            <IconClipboardList size={20} />
          </ThemeIcon>
          <Title order={2} style={{ fontSize: "20px", fontWeight: 500 }}>Shift Handover</Title>
        </Group>
        <Button variant="light" color="blue" onClick={() => window.print()}>
          Print Handover Log
        </Button>
      </Group>

      {/* Incoming — acknowledge pending */}
      {pendingHandovers.length > 0 && (
        <Card withBorder radius="md" p="lg" style={{ borderLeftWidth: 3, borderLeftColor: "var(--mantine-color-orange-5)" }}>
          <Group justify="space-between" mb="md">
            <Text fw={700} c="orange">
              Incoming Handovers ({pendingHandovers.length} pending acknowledgement)
            </Text>
            <Button
              size="xs"
              variant="light"
              color="green"
              leftSection={<IconCheck size={14} />}
              loading={ackAllMutation.isPending}
              onClick={() => ackAllMutation.mutate(pendingHandovers.map((h) => h.id))}
            >
              Acknowledge all
            </Button>
          </Group>
          <Stack gap="sm">
            {pendingHandovers.map((h) => (
              <Card key={h.id} withBorder radius="sm" p="md" bg="var(--bg-amber)">
                <Group justify="space-between" mb="xs">
                  <Group gap="xs">
                    <Text size="sm" fw={600}>{h.from_user_name}</Text>
                    {h.to_user_name && (
                      <>
                        <IconArrowRight size={14} />
                        <Text size="sm" fw={600}>{h.to_user_name}</Text>
                      </>
                    )}
                    {h.ward_name && <Badge size="xs" variant="outline">{h.ward_name}</Badge>}
                  </Group>
                  <Group gap="xs">
                    <Text size="xs" c="dimmed">{dayjs(h.created_at).format("HH:mm DD MMM")}</Text>
                    <Button
                      size="xs"
                      color="green"
                      variant="light"
                      leftSection={<IconCheck size={12} />}
                      loading={ackMutation.isPending && ackMutation.variables === h.id}
                      onClick={() => ackMutation.mutate(h.id)}
                    >
                      Acknowledge
                    </Button>
                  </Group>
                </Group>
                <Text size="sm" style={{ whiteSpace: "pre-wrap" }}>{h.summary}</Text>
              </Card>
            ))}
          </Stack>
        </Card>
      )}

      {/* Patients in ward — quick reference */}
      {patients.length > 0 && (
        <Card withBorder radius="md" p="lg">
          <Text fw={600} mb="sm">Current Patients on Ward</Text>
          <Table.ScrollContainer minWidth={400}>
            <Table striped withTableBorder withColumnBorders>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Patient NHID</Table.Th>
                  <Table.Th>Ward</Table.Th>
                  <Table.Th>Bed</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {patients.map((p) => (
                  <Table.Tr key={`${p.nhid}-${p.bed}`}>
                    <Table.Td><Text size="sm" ff="monospace" c="blue">{p.nhid}</Text></Table.Td>
                    <Table.Td><Text size="sm">{p.ward}</Text></Table.Td>
                    <Table.Td><Text size="sm">{p.bed}</Text></Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        </Card>
      )}

      {/* Create handover form */}
      <Card withBorder radius="lg" p="lg">
        <Text fw={600} mb="md">Submit Outgoing Handover</Text>
        <form onSubmit={form.onSubmit((v) => mutation.mutate(v))}>
          <Stack gap="md">
            <Textarea
              label="Overall ward summary"
              description="Key updates, admissions, discharges and general ward status."
              placeholder="e.g. Ward relatively stable. 12 patients. 2 new admissions overnight. Patient in Bed A4 deteriorating…"
              minRows={4}
              required
              {...form.getInputProps("summary")}
            />
            <Textarea
              label="Pending tasks"
              description="Tasks that must be completed by the incoming team."
              placeholder="e.g. IV antibiotics for Bed B2 due at 22:00. Blood cultures for Bed C1 not yet sent…"
              minRows={3}
              {...form.getInputProps("pending_tasks")}
            />
            <Textarea
              label="Concerns / monitoring"
              description="Patients requiring close observation."
              placeholder="e.g. Bed D3 — post-op patient, monitor urine output hourly. Alert if BP falls below 90/60…"
              minRows={3}
              {...form.getInputProps("concerns")}
            />
            <Textarea
              label="Items for next shift"
              description="Information, decisions, or follow-ups needed in the next shift."
              placeholder="e.g. Await chest X-ray result for Bed A2. Surgeon review for Bed C4 requested for morning round…"
              minRows={2}
              {...form.getInputProps("next_shift")}
            />
            <Group justify="flex-end">
              <Button type="submit" loading={mutation.isPending} rightSection={<IconArrowRight size={16} />}>
                Submit Handover
              </Button>
            </Group>
          </Stack>
        </form>
      </Card>

      <Divider label="Previous Handovers" labelPosition="left" />

      {isLoading ? (
        <Stack gap="sm">{[1, 2].map((i) => <Skeleton key={i} height={100} radius="md" />)}</Stack>
      ) : !data?.length ? (
        <Box ta="center" py="xl">
          <Text c="dimmed" size="sm">No handover notes on record.</Text>
        </Box>
      ) : (
        <Stack gap="sm">
          {(data ?? []).map((h) => (
            <Card key={h.id} withBorder radius="md" p="md">
              <Group justify="space-between" mb="xs">
                <Group gap="xs">
                  <Text size="sm" fw={600}>{h.from_user_name}</Text>
                  {h.to_user_name && (
                    <>
                      <IconArrowRight size={14} />
                      <Text size="sm" fw={600}>{h.to_user_name}</Text>
                    </>
                  )}
                  {h.ward_name && <Text size="xs" c="dimmed">· {h.ward_name}</Text>}
                </Group>
                <Group gap="xs">
                  <Text size="xs" c="dimmed">{dayjs(h.created_at).format("DD MMM YYYY HH:mm")}</Text>
                  {h.acknowledged_at && (
                    <Badge color="green" size="xs" variant="light">
                      <IconCheck size={10} /> Acknowledged by {h.acknowledged_by_name}
                    </Badge>
                  )}
                </Group>
              </Group>
              <Text size="sm" style={{ whiteSpace: "pre-wrap" }}>{h.summary}</Text>
            </Card>
          ))}
        </Stack>
      )}
    </Stack>
  );
}
