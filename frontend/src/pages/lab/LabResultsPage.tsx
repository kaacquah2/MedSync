/**
 * LabResultsPage — lab technician result entry.
 *
 * Lab tech selects a pending order (patient + test pre-filled),
 * enters results with inline reference ranges, auto-flags abnormals,
 * and can mark a "critical value" that triggers a prominent alert.
 */

import {
  Alert,
  Badge,
  Box,
  Button,
  Card,
  Checkbox,
  Divider,
  Group,
  Select,
  SimpleGrid,
  Skeleton,
  Stack,
  Table,
  Text,
  Textarea,
  TextInput,
  ThemeIcon,
  Title,
} from "@mantine/core";
import { useForm } from "@mantine/form";
import { notifications } from "@mantine/notifications";
import {
  IconAlertTriangle,
  IconCheck,
  IconFlask,
  IconUrgent,
} from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, useMemo, useEffect } from "react";
import { createLabResult, fetchLabWorklist } from "@/api/endpoints";

interface FieldRefRange {
  key: string;
  label: string;
  placeholder: string;
  low?: number;
  high?: number;
  unit: string;
  type?: "number" | "select" | "text";
  options?: { value: string; label: string }[];
}

interface RefRange {
  unit: string;
  fields: FieldRefRange[];
}

const REF_RANGES: Record<string, RefRange> = {
  "full blood count": {
    unit: "multiparameter",
    fields: [
      { key: "hb", label: "Haemoglobin", placeholder: "12.0 - 17.0", low: 12.0, high: 17.0, unit: "g/dL", type: "number" },
      { key: "wbc", label: "WBC", placeholder: "4.0 - 11.0", low: 4.0, high: 11.0, unit: "x10⁹/L", type: "number" },
      { key: "platelets", label: "Platelets", placeholder: "150 - 400", low: 150, high: 400, unit: "x10⁹/L", type: "number" },
    ]
  },
  "fbc": {
    unit: "multiparameter",
    fields: [
      { key: "hb", label: "Haemoglobin", placeholder: "12.0 - 17.0", low: 12.0, high: 17.0, unit: "g/dL", type: "number" },
      { key: "wbc", label: "WBC", placeholder: "4.0 - 11.0", low: 4.0, high: 11.0, unit: "x10⁹/L", type: "number" },
      { key: "platelets", label: "Platelets", placeholder: "150 - 400", low: 150, high: 400, unit: "x10⁹/L", type: "number" },
    ]
  },
  "malaria": {
    unit: "malaria",
    fields: [
      {
        key: "rdt",
        label: "Malaria RDT Status",
        placeholder: "Select...",
        type: "select",
        unit: "",
        options: [
          { value: "Negative", label: "Negative" },
          { value: "Positive", label: "Positive" },
        ]
      },
      { key: "smear", label: "Blood Film Smear (Parasite Density)", placeholder: "e.g. +, ++, or 2500/uL", unit: "parasites/uL", type: "text" },
    ]
  },
  "biochemistry": {
    unit: "biochem",
    fields: [
      { key: "glucose", label: "Fasting Blood Glucose", placeholder: "3.9 - 7.8", low: 3.9, high: 7.8, unit: "mmol/L", type: "number" },
      { key: "creatinine", label: "Creatinine", placeholder: "53 - 106", low: 53, high: 106, unit: "µmol/L", type: "number" },
      { key: "alt", label: "ALT (Alanine Aminotransferase)", placeholder: "7 - 40", low: 7, high: 40, unit: "U/L", type: "number" },
      { key: "ast", label: "AST (Aspartate Aminotransferase)", placeholder: "10 - 40", low: 10, high: 40, unit: "U/L", type: "number" },
    ]
  },
  "default": {
    unit: "general",
    fields: [
      { key: "result_value", label: "Result Value", placeholder: "Enter findings", unit: "", type: "text" }
    ]
  }
};

function getRangeForTest(testName: string): RefRange {
  const lower = testName.toLowerCase();
  if (lower.includes("fbc") || lower.includes("blood count") || lower.includes("haematology")) {
    return REF_RANGES["full blood count"];
  }
  if (lower.includes("malaria")) {
    return REF_RANGES["malaria"];
  }
  if (lower.includes("biochem") || lower.includes("glucose") || lower.includes("lft") || lower.includes("creatinine")) {
    return REF_RANGES["biochemistry"];
  }
  return REF_RANGES["default"];
}

function isFieldAbnormal(val: string, fRange: FieldRefRange): boolean {
  if (!val) return false;
  if (fRange.type === "select" && val === "Positive") return true;
  if (fRange.type === "number") {
    const num = parseFloat(val);
    if (isNaN(num)) return false;
    if (fRange.low !== undefined && num < fRange.low) return true;
    if (fRange.high !== undefined && num > fRange.high) return true;
  }
  return false;
}

export function LabResultsPage() {
  const qc = useQueryClient();
  const [selectedOrderId, setSelectedOrderId] = useState<string | null>(null);
  const [isCritical, setIsCritical] = useState(false);
  const [notifyDoctor, setNotifyDoctor] = useState(false);
  const [fieldValues, setFieldValues] = useState<Record<string, string>>({});

  const { data: orders, isLoading } = useQuery({
    queryKey: ["lab-worklist"],
    queryFn: () => fetchLabWorklist().then((r) => r.data),
    refetchInterval: 30_000,
  });

  const pendingOrders = (orders ?? []).filter(
    (o) => o.status === "pending" || o.status === "in_progress"
  );

  const selectedOrder = pendingOrders.find((o) => String(o.id) === selectedOrderId);
  const range = useMemo(
    () => (selectedOrder ? getRangeForTest(selectedOrder.test_name) : REF_RANGES["default"]),
    [selectedOrder]
  );

  const form = useForm({
    initialValues: {
      reference_range: "",
      loinc_code: "",
      is_abnormal: false,
      notes: "",
    },
  });

  // Calculate if any individual field is abnormal based on the rules
  const hasAbnormalFields = useMemo(() => {
    return range.fields.some((f) => isFieldAbnormal(fieldValues[f.key] || "", f));
  }, [fieldValues, range]);

  // Sync abnormal state automatically when fields update
  useEffect(() => {
    form.setFieldValue("is_abnormal", hasAbnormalFields);
  }, [hasAbnormalFields]);

  // Build result_value string
  const computedResult = useMemo(() => {
    if (range.fields.length === 1 && range.fields[0].type === "text") {
      return fieldValues[range.fields[0].key] ?? "";
    }
    return range.fields
      .map((f) => {
        const val = fieldValues[f.key] || "—";
        const abnStr = isFieldAbnormal(val, f) ? " (Abnormal)" : "";
        return `${f.label}: ${val} ${f.unit}${abnStr}`;
      })
      .join(" | ");
  }, [fieldValues, range]);

  const mutation = useMutation({
    mutationFn: () => {
      if (!selectedOrder?.encounter) throw new Error("No encounter linked to this order.");
      
      const referenceRangeText = range.fields
        .map((f) => f.low !== undefined ? `${f.label}: ${f.low}-${f.high} ${f.unit}` : "")
        .filter(Boolean)
        .join(" | ") || "As specified";

      return createLabResult(selectedOrder.encounter, {
        test_name:       selectedOrder.test_name,
        loinc_code:      selectedOrder.loinc_code || form.values.loinc_code || undefined,
        result_value:    computedResult,
        reference_range: referenceRangeText,
        is_abnormal:     form.values.is_abnormal || isCritical,
      });
    },
    onSuccess: () => {
      notifications.show({ color: "green", icon: <IconCheck />, message: "Lab result recorded." });
      
      if (notifyDoctor) {
        notifications.show({
          title: "Critical Result Flagged",
          message: "Result marked as abnormal — it will appear in the ordering doctor's alerts feed immediately.",
          color: "orange",
        });
      }

      setSelectedOrderId(null);
      setFieldValues({});
      setIsCritical(false);
      setNotifyDoctor(false);
      form.reset();
      qc.invalidateQueries({ queryKey: ["lab-worklist"] });
    },
    onError: (e: unknown) =>
      notifications.show({ color: "red", message: e instanceof Error ? e.message : "Failed to save result." }),
  });

  const orderOptions = pendingOrders.map((o) => ({
    value: String(o.id),
    label: `#${o.id} · ${o.test_name} — ${o.patient_nhid} (${o.priority_display})`,
  }));

  return (
    <Stack gap="lg">
      <Group gap="xs">
        <ThemeIcon size={36} color="teal" variant="light" radius="md">
          <IconFlask size={20} />
        </ThemeIcon>
        <Box>
          <Title order={2} style={{ fontSize: "20px", fontWeight: 500 }}>Lab Result Entry</Title>
          <Text size="xs" c="dimmed">Record parameters and auto-apply clinical alerts</Text>
        </Box>
      </Group>

      {isCritical && (
        <Alert
          color="red"
          icon={<IconUrgent />}
          title="CRITICAL VALUE ALERT"
          variant="filled"
        >
          This result has been marked as a critical value. The ordering physician will be paged
          immediately. Check the physician notification box to trigger automated alerts.
        </Alert>
      )}

      <SimpleGrid cols={{ base: 1, lg: 2 }} spacing="lg">
        {/* Left — entry form */}
        <Card withBorder radius="md" p="lg">
          <Text fw={600} size="sm" tt="uppercase" c="dimmed" mb="md">Enter Result Data</Text>

          {isLoading ? (
            <Stack gap="xs">{[1,2,3].map((i) => <Skeleton key={i} height={48} />)}</Stack>
          ) : (
            <Stack gap="sm">
              <Select
                label="Select Lab Order"
                placeholder="Choose a pending order…"
                data={orderOptions}
                value={selectedOrderId}
                onChange={(v) => { setSelectedOrderId(v); setFieldValues({}); setIsCritical(false); form.reset(); }}
                searchable
                nothingFoundMessage="No pending orders"
                required
              />

              {selectedOrder && (
                <>
                  <SimpleGrid cols={2} spacing="sm">
                    <TextInput label="Patient NHID" value={selectedOrder.patient_nhid} readOnly styles={{ input: { background: "var(--surface-0)" } }} />
                    <TextInput label="Test type" value={selectedOrder.test_name} readOnly styles={{ input: { background: "var(--surface-0)" } }} />
                  </SimpleGrid>

                  <Divider label="Parameters & Reference Ranges" labelPosition="left" my="xs" />

                  {/* Dynamic fields with sub-field validation */}
                  {range.fields.map((field) => {
                    const val = fieldValues[field.key] ?? "";
                    const outRange = isFieldAbnormal(val, field);
                    
                    if (field.type === "select") {
                      return (
                        <Select
                          key={field.key}
                          label={field.label}
                          data={field.options || []}
                          value={val}
                          onChange={(v) => setFieldValues((prev) => ({ ...prev, [field.key]: v || "" }))}
                          styles={outRange ? { input: { borderColor: "var(--accent-red)", background: "var(--bg-red)", color: "var(--accent-red)" } } : {}}
                          rightSection={outRange ? <IconAlertTriangle size={16} color="var(--accent-red)" /> : null}
                        />
                      );
                    }

                    return (
                      <Box key={field.key}>
                        <TextInput
                          label={
                            <Group gap={4}>
                              <Text size="sm">{field.label}</Text>
                              {field.low !== undefined && (
                                <Badge size="xs" color="gray" variant="outline">
                                  Ref: {field.low}–{field.high} {field.unit}
                                </Badge>
                              )}
                            </Group>
                          }
                          placeholder={field.placeholder}
                          value={val}
                          onChange={(e) => setFieldValues((prev) => ({ ...prev, [field.key]: e.target.value }))}
                          styles={outRange ? { input: { borderColor: "var(--accent-red)", background: "var(--bg-red)", color: "var(--accent-red)", fontWeight: 600 } } : {}}
                          rightSection={outRange ? <IconAlertTriangle size={16} color="var(--accent-red)" /> : null}
                        />
                        {outRange && (
                          <Text size="xs" c="var(--accent-red)" fw={600} mt={2}>
                            ⚠ Value outside normal range
                          </Text>
                        )}
                      </Box>
                    );
                  })}

                  <Divider my="xs" />

                  <Checkbox
                    label="Mark as abnormal / out of range"
                    checked={form.values.is_abnormal}
                    onChange={(e) => form.setFieldValue("is_abnormal", e.target.checked)}
                  />
                  <Checkbox
                    label={<Text fw={600} c="red">🔴 Critical value — requires immediate physician notification</Text>}
                    checked={isCritical}
                    onChange={(e) => setIsCritical(e.target.checked)}
                    color="red"
                  />
                  <Checkbox
                    label="Flag critical result — appears in doctor's alerts feed immediately"
                    checked={notifyDoctor}
                    onChange={(e) => setNotifyDoctor(e.target.checked)}
                    color="orange"
                  />

                  <Textarea
                    label="Lab Comments / Notes"
                    placeholder="Specimen notes, dilution factors, or clinical interpretations"
                    rows={2}
                    {...form.getInputProps("notes")}
                  />

                  <Group justify="flex-end" mt="md">
                    <Button
                      color="teal"
                      leftSection={<IconCheck size={16} />}
                      loading={mutation.isPending}
                      onClick={() => mutation.mutate()}
                      disabled={!computedResult.trim()}
                    >
                      Submit Lab Results
                    </Button>
                  </Group>
                </>
              )}
            </Stack>
          )}
        </Card>

        {/* Right — pending orders table */}
        <Card withBorder radius="md" p="lg" bg="var(--surface-2)">
          <Text fw={600} size="sm" tt="uppercase" c="dimmed" mb="md">Pending Orders ({pendingOrders.length})</Text>
          {isLoading ? (
            <Stack gap="xs">{[1,2,3,4].map((i) => <Skeleton key={i} height={44} />)}</Stack>
          ) : !pendingOrders.length ? (
            <Box ta="center" py="xl"><Text c="dimmed" size="sm">No pending orders.</Text></Box>
          ) : (
            <Table.ScrollContainer minWidth={400}>
              <Table striped highlightOnHover>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>Order</Table.Th>
                    <Table.Th>Test</Table.Th>
                    <Table.Th>Patient</Table.Th>
                    <Table.Th>Priority</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {pendingOrders.map((o) => (
                    <Table.Tr
                      key={o.id}
                      onClick={() => setSelectedOrderId(String(o.id))}
                      style={{ cursor: "pointer", background: String(o.id) === selectedOrderId ? "var(--surface-0)" : undefined }}
                    >
                      <Table.Td><Text size="xs" ff="monospace">#{o.id}</Text></Table.Td>
                      <Table.Td><Text size="sm" fw={600}>{o.test_name}</Text></Table.Td>
                      <Table.Td><Text size="xs" ff="monospace">{o.patient_nhid}</Text></Table.Td>
                      <Table.Td>
                        <Badge
                          size="xs"
                          color={o.priority === "stat" ? "red" : o.priority === "urgent" ? "orange" : "blue"}
                          variant={o.priority === "stat" ? "filled" : "light"}
                        >
                          {o.priority_display}
                        </Badge>
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </Table.ScrollContainer>
          )}
        </Card>
      </SimpleGrid>
    </Stack>
  );
}
