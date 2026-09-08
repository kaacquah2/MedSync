/**
 * VitalsPage — nurse/doctor vitals entry form.
 *
 * Patient selector → fills in all vital fields.
 * Auto-highlights out-of-range values in red.
 * Uses createVitalSign API.
 */

import {
  Alert,
  Badge,
  Box,
  Button,
  Card,
  Group,
  NumberInput,
  Select,
  SimpleGrid,
  Skeleton,
  Stack,
  Table,
  Text,
  ThemeIcon,
  Title,
} from "@mantine/core";
import { useForm } from "@mantine/form";
import { notifications } from "@mantine/notifications";
import {
  IconAlertTriangle,
  IconCheck,
  IconHeartbeat,
  IconSearch,
} from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import dayjs from "dayjs";
import { useState } from "react";
import { createVitalSign, fetchPatientVitals, searchPatients } from "@/api/endpoints";

// ── Clinical reference ranges ─────────────────────────────────────────────────
interface VitalRange { low?: number; high?: number; unit: string; label: string; description?: string; }

const RANGES: Record<string, VitalRange> = {
  bp_systolic:       { low: 90,  high: 140, unit: "mmHg",       label: "BP Systolic",       description: "Normal: 90–140 mmHg" },
  bp_diastolic:      { low: 60,  high: 90,  unit: "mmHg",       label: "BP Diastolic",       description: "Normal: 60–90 mmHg" },
  temperature:       { low: 36.0,high: 37.5,unit: "°C",         label: "Temperature",         description: "Normal: 36.0–37.5 °C" },
  heart_rate:        { low: 60,  high: 100, unit: "bpm",         label: "Heart Rate",          description: "Normal: 60–100 bpm" },
  respiratory_rate:  { low: 12,  high: 20,  unit: "br/min",      label: "Respiratory Rate",    description: "Normal: 12–20 breaths/min" },
  spo2:              { low: 95,  high: 100, unit: "%",            label: "SpO₂",                description: "Normal: ≥95%" },
  weight_kg:         { unit: "kg",          label: "Weight",      description: "Enter in kg" },
  pain_score:        { low: 0,   high: 10,  unit: "/10",          label: "Pain Score",          description: "0 = none, 10 = worst" },
};

// ── Hard Physiological Limits (Enforced strictly on frontend & backend) ───────────
export interface PhysiologicalBoundary {
  min: number;
  max: number;
  label: string;
  unit: string;
}

export const PHYSIOLOGICAL_BOUNDS: Record<string, PhysiologicalBoundary> = {
  temperature:      { min: 30.0, max: 45.0, label: "Temperature",      unit: "°C" },
  heart_rate:       { min: 20,   max: 300,  label: "Heart Rate",       unit: "bpm" },
  bp_systolic:      { min: 50,   max: 250,  label: "BP Systolic",      unit: "mmHg" },
  bp_diastolic:     { min: 30,   max: 150,  label: "BP Diastolic",     unit: "mmHg" },
  spo2:             { min: 50,   max: 100,  label: "SpO₂",             unit: "%" },
  pain_score:       { min: 0,    max: 10,   label: "Pain Score",       unit: "/10" },
  respiratory_rate: { min: 4,    max: 80,   label: "Respiratory Rate", unit: "br/min" },
  weight_kg:        { min: 0.5,  max: 500,  label: "Weight",           unit: "kg" },
};

export const GLUCOSE_BOUNDS = { min: 0.5, max: 50, label: "Blood Glucose", unit: "mmol/L" };

export interface VitalsFormValues {
  bp_systolic: number | undefined;
  bp_diastolic: number | undefined;
  temperature: number | undefined;
  heart_rate: number | undefined;
  respiratory_rate: number | undefined;
  spo2: number | undefined;
  weight_kg: number | undefined;
  pain_score: number | undefined;
}

export function validateVitalsForm(values: VitalsFormValues): Record<string, string | null> {
  const errors: Record<string, string | null> = {};

  for (const [key, bounds] of Object.entries(PHYSIOLOGICAL_BOUNDS)) {
    const val = values[key as keyof VitalsFormValues];
    if (val !== undefined && val !== null && !isNaN(val)) {
      if (val < bounds.min || val > bounds.max) {
        errors[key] = `${bounds.label} must be between ${bounds.min} and ${bounds.max} ${bounds.unit}.`;
      }
    }
  }

  // Cross-field validation: Systolic must be strictly greater than Diastolic
  if (
    values.bp_systolic !== undefined &&
    values.bp_systolic !== null &&
    values.bp_diastolic !== undefined &&
    values.bp_diastolic !== null &&
    !isNaN(values.bp_systolic) &&
    !isNaN(values.bp_diastolic)
  ) {
    if (values.bp_systolic <= values.bp_diastolic) {
      errors.bp_systolic = "Systolic blood pressure must be greater than diastolic blood pressure.";
    }
  }

  return errors;
}

// Blood glucose range definition (GLUCOSE_BOUNDS 0.5–50 mmol/L)
const GLUCOSE_RANGE: VitalRange = { low: 3.9, high: 7.8, unit: "mmol/L", label: "Blood Glucose", description: "Normal fasting: 3.9–7.8 mmol/L" };

function isOutOfRange(value: number | undefined, range: VitalRange): boolean {
  if (value === undefined || value === null) return false;
  if (range.low !== undefined && value < range.low) return true;
  if (range.high !== undefined && value > range.high) return true;
  return false;
}

function RangeHighlightInput({
  field,
  range,
  value,
  onChange,
  error,
}: {
  field: string;
  range: VitalRange;
  value: number | undefined;
  onChange: (v: number | string) => void;
  error?: React.ReactNode;
}) {
  const out = isOutOfRange(value, range);
  return (
    <Box>
      <NumberInput
        label={
          <Group gap={4}>
            <Text size="sm">{range.label}</Text>
            {range.description && (
              <Badge size="xs" color="gray" variant="outline">{range.description}</Badge>
            )}
          </Group>
        }
        placeholder={`${range.low ?? ""}${range.high ? `–${range.high}` : ""} ${range.unit}`}
        suffix={` ${range.unit}`}
        value={value ?? ""}
        onChange={onChange}
        step={field === "temperature" ? 0.1 : 1}
        decimalScale={field === "temperature" ? 1 : 0}
        styles={
          error
            ? {}
            : out
            ? { input: { borderColor: "var(--accent-red)", background: "var(--bg-red)", color: "var(--accent-red)", fontWeight: 600 } }
            : {}
        }
        rightSection={!error && out ? <IconAlertTriangle size={16} color="var(--accent-red)" /> : null}
        error={error}
        min={0}
      />
      {!error && out && (
        <Text size="xs" c="var(--accent-red)" fw={600} mt={2}>
          ⚠ Outside normal range ({range.low}–{range.high} {range.unit})
        </Text>
      )}
    </Box>
  );
}

function formatApiError(err: unknown, fallback: string): string {
  const data = (err as { response?: { data?: unknown } })?.response?.data;
  if (!data) return fallback;
  if (typeof data === "string") return data;
  if (typeof data === "object") {
    if ("error" in data && typeof (data as { error: string }).error === "string") {
      return (data as { error: string }).error;
    }
    if ("detail" in data && typeof (data as { detail: string }).detail === "string") {
      return (data as { detail: string }).detail;
    }
    const messages: string[] = [];
    for (const [key, val] of Object.entries(data as Record<string, unknown>)) {
      if (Array.isArray(val)) {
        messages.push(`${key}: ${val.join(", ")}`);
      } else if (typeof val === "string") {
        messages.push(`${key}: ${val}`);
      }
    }
    if (messages.length > 0) return messages.join(" | ");
  }
  return fallback;
}

export function VitalsPage() {
  const qc = useQueryClient();
  const [patientSearch, setPatientSearch] = useState("");
  const [selectedNhid, setSelectedNhid] = useState<string | null>(null);
  const [glucose, setGlucose] = useState<number | undefined>();
  const [glucoseError, setGlucoseError] = useState<string | null>(null);

  const { data: searchData, isLoading: searching } = useQuery({
    queryKey: ["vitals-patient-search", patientSearch],
    queryFn:  () => searchPatients(patientSearch).then((r) => r.data),
    enabled:  patientSearch.length >= 2,
    staleTime: 10_000,
  });

  const { data: prevVitals, isLoading: loadingVitals } = useQuery({
    queryKey: ["patient-vitals", selectedNhid],
    queryFn:  () => fetchPatientVitals(selectedNhid!).then((r) => r.data),
    enabled:  !!selectedNhid,
  });

  const patientOptions = searchData?.results.map((p) => ({
    value: p.universal_id,
    label: `${p.full_name} — ${p.universal_id}`,
  })) ?? [];

  const form = useForm<VitalsFormValues>({
    initialValues: {
      bp_systolic:      undefined,
      bp_diastolic:     undefined,
      temperature:      undefined,
      heart_rate:       undefined,
      respiratory_rate: undefined,
      spo2:             undefined,
      weight_kg:        undefined,
      pain_score:       undefined,
    },
    validate: validateVitalsForm,
  });

  const anyAbnormal = (Object.keys(RANGES) as (keyof typeof RANGES)[]).some((k) =>
    isOutOfRange(form.values[k as keyof typeof form.values] as number | undefined, RANGES[k])
  ) || isOutOfRange(glucose, GLUCOSE_RANGE);

  const handleGlucoseChange = (v: number | string) => {
    const val = v === "" ? undefined : (v as number);
    setGlucose(val);
    if (val !== undefined && !isNaN(val) && (val < GLUCOSE_BOUNDS.min || val > GLUCOSE_BOUNDS.max)) {
      setGlucoseError(`Blood glucose must be between ${GLUCOSE_BOUNDS.min} and ${GLUCOSE_BOUNDS.max} mmol/L.`);
    } else {
      setGlucoseError(null);
    }
  };

  const mutation = useMutation({
    mutationFn: () => {
      if (!selectedNhid) throw new Error("No patient selected.");
      return createVitalSign(selectedNhid, {
        ...form.values,
        blood_glucose: glucose,
        recorded_at: new Date().toISOString(),
      });
    },
    onSuccess: () => {
      notifications.show({ color: "green", icon: <IconCheck />, message: "Vitals recorded." });
      form.reset();
      setGlucose(undefined);
      setGlucoseError(null);
      qc.invalidateQueries({ queryKey: ["patient-vitals", selectedNhid] });
    },
    onError: (e: unknown) =>
      notifications.show({ color: "red", message: formatApiError(e, "Failed to record vitals.") }),
  });

  const handleSubmit = form.onSubmit(() => {
    if (glucoseError) return;
    const values = form.values;
    const hasAtLeastOne = Object.values(values).some((v) => v !== undefined && v !== null && v !== "");
    if (!hasAtLeastOne && glucose === undefined) {
      notifications.show({ color: "red", message: "Please enter at least one vital sign observation." });
      return;
    }
    mutation.mutate();
  });

  return (
    <Stack gap="lg">
      <Group gap="xs">
        <ThemeIcon size={36} color="pink" variant="light" radius="md">
          <IconHeartbeat size={20} />
        </ThemeIcon>
        <Box>
          <Title order={2}>Vitals Entry</Title>
          <Text size="xs" c="dimmed">Record patient observations — abnormal values highlighted automatically</Text>
        </Box>
      </Group>

      {anyAbnormal && (
        <Alert color="orange" icon={<IconAlertTriangle />} title="Abnormal Values Detected">
          One or more vital signs are outside normal range. Review before submitting and notify the attending clinician.
        </Alert>
      )}

      <SimpleGrid cols={{ base: 1, lg: 2 }} spacing="lg">
        {/* Left — form */}
        <Card withBorder radius="md" p="lg">
          <Text fw={700} mb="md">Record New Vitals</Text>

          <Stack gap="sm">
            {/* Patient selector */}
            <Select
              label="Patient"
              placeholder="Search by name or NHID…"
              leftSection={<IconSearch size={16} />}
              searchable
              data={patientOptions}
              onSearchChange={setPatientSearch}
              value={selectedNhid}
              onChange={(v) => setSelectedNhid(v)}
              nothingFoundMessage={patientSearch.length < 2 ? "Type at least 2 characters" : searching ? "Searching…" : "No patients found"}
              required
            />

            <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm">
              <RangeHighlightInput
                field="bp_systolic"
                range={RANGES.bp_systolic}
                value={form.values.bp_systolic}
                onChange={(v) => form.setFieldValue("bp_systolic", v === "" ? undefined : (v as number))}
                error={form.errors.bp_systolic}
              />
              <RangeHighlightInput
                field="bp_diastolic"
                range={RANGES.bp_diastolic}
                value={form.values.bp_diastolic}
                onChange={(v) => form.setFieldValue("bp_diastolic", v === "" ? undefined : (v as number))}
                error={form.errors.bp_diastolic}
              />
              <RangeHighlightInput
                field="temperature"
                range={RANGES.temperature}
                value={form.values.temperature}
                onChange={(v) => form.setFieldValue("temperature", v === "" ? undefined : (v as number))}
                error={form.errors.temperature}
              />
              <RangeHighlightInput
                field="heart_rate"
                range={RANGES.heart_rate}
                value={form.values.heart_rate}
                onChange={(v) => form.setFieldValue("heart_rate", v === "" ? undefined : (v as number))}
                error={form.errors.heart_rate}
              />
              <RangeHighlightInput
                field="respiratory_rate"
                range={RANGES.respiratory_rate}
                value={form.values.respiratory_rate}
                onChange={(v) => form.setFieldValue("respiratory_rate", v === "" ? undefined : (v as number))}
                error={form.errors.respiratory_rate}
              />
              <RangeHighlightInput
                field="spo2"
                range={RANGES.spo2}
                value={form.values.spo2}
                onChange={(v) => form.setFieldValue("spo2", v === "" ? undefined : (v as number))}
                error={form.errors.spo2}
              />
              <RangeHighlightInput
                field="weight_kg"
                range={RANGES.weight_kg}
                value={form.values.weight_kg}
                onChange={(v) => form.setFieldValue("weight_kg", v === "" ? undefined : (v as number))}
                error={form.errors.weight_kg}
              />
              <RangeHighlightInput
                field="pain_score"
                range={RANGES.pain_score}
                value={form.values.pain_score}
                onChange={(v) => form.setFieldValue("pain_score", v === "" ? undefined : (v as number))}
                error={form.errors.pain_score}
              />
            </SimpleGrid>

            {/* Blood glucose — extra field */}
            <RangeHighlightInput
              field="glucose"
              range={GLUCOSE_RANGE}
              value={glucose}
              onChange={handleGlucoseChange}
              error={glucoseError}
            />

            <Group justify="flex-end" mt="xs">
              <Button variant="subtle" onClick={() => { form.reset(); setGlucose(undefined); setGlucoseError(null); }}>
                Clear
              </Button>
              <Button
                color="pink"
                leftSection={<IconCheck size={16} />}
                loading={mutation.isPending}
                onClick={() => handleSubmit()}
                disabled={!selectedNhid}
              >
                Save Vitals
              </Button>
            </Group>
          </Stack>
        </Card>

        {/* Right — previous vitals */}
        <Card withBorder radius="md" p="lg">
          <Text fw={700} mb="md">
            {selectedNhid ? "Previous Vitals" : "Select a patient to view history"}
          </Text>

          {!selectedNhid ? (
            <Box ta="center" py="xl"><Text c="dimmed" size="sm">No patient selected.</Text></Box>
          ) : loadingVitals ? (
            <Stack gap="xs">{[1,2,3].map((i) => <Skeleton key={i} height={60} />)}</Stack>
          ) : !prevVitals?.length ? (
            <Box ta="center" py="xl"><Text c="dimmed" size="sm">No vitals recorded yet.</Text></Box>
          ) : (
            <Stack gap="xs">
              {prevVitals.slice(0, 5).map((v) => (
                <Card key={v.id} withBorder radius="sm" p="sm">
                  <Group justify="space-between" mb={4}>
                    <Text size="xs" c="dimmed">{dayjs(v.recorded_at).format("DD MMM YYYY HH:mm")}</Text>
                    <Text size="xs" c="dimmed">{v.recorded_by_name}</Text>
                  </Group>
                  <Group gap="xs" wrap="wrap">
                    {v.bp_systolic && v.bp_diastolic && (
                      <Badge size="sm" color={isOutOfRange(v.bp_systolic, RANGES.bp_systolic) ? "red" : "blue"} variant="light">
                        BP {v.bp_systolic}/{v.bp_diastolic} mmHg
                      </Badge>
                    )}
                    {v.temperature && (
                      <Badge size="sm" color={isOutOfRange(v.temperature, RANGES.temperature) ? "red" : "teal"} variant="light">
                        T {v.temperature} °C
                      </Badge>
                    )}
                    {v.heart_rate && (
                      <Badge size="sm" color={isOutOfRange(v.heart_rate, RANGES.heart_rate) ? "red" : "pink"} variant="light">
                        HR {v.heart_rate} bpm
                      </Badge>
                    )}
                    {v.spo2 && (
                      <Badge size="sm" color={isOutOfRange(v.spo2, RANGES.spo2) ? "red" : "cyan"} variant="light">
                        SpO₂ {v.spo2}%
                      </Badge>
                    )}
                    {v.weight_kg && (
                      <Badge size="sm" color="gray" variant="light">
                        Wt {v.weight_kg} kg
                      </Badge>
                    )}
                    {v.blood_glucose && (
                      <Badge size="sm" color={isOutOfRange(v.blood_glucose, GLUCOSE_RANGE) ? "red" : "orange"} variant="light">
                        BG {v.blood_glucose} mmol/L
                      </Badge>
                    )}
                  </Group>
                </Card>
              ))}
            </Stack>
          )}
        </Card>
      </SimpleGrid>

      {/* Reference ranges quick reference */}
      <Card withBorder radius="md" p="lg">
        <Text fw={600} mb="sm">Normal Reference Ranges — Quick Reference</Text>
        <Table withTableBorder withColumnBorders>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Parameter</Table.Th>
              <Table.Th>Normal Range</Table.Th>
              <Table.Th>Unit</Table.Th>
              <Table.Th>Critical Low</Table.Th>
              <Table.Th>Critical High</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {[
              { name: "BP Systolic", low: 90, high: 140, unit: "mmHg", critLow: "<80", critHigh: ">180" },
              { name: "BP Diastolic", low: 60, high: 90, unit: "mmHg", critLow: "<50", critHigh: ">110" },
              { name: "Temperature", low: 36.0, high: 37.5, unit: "°C", critLow: "<35.0", critHigh: ">40.0" },
              { name: "Heart Rate", low: 60, high: 100, unit: "bpm", critLow: "<40", critHigh: ">150" },
              { name: "Respiratory Rate", low: 12, high: 20, unit: "br/min", critLow: "<8", critHigh: ">30" },
              { name: "SpO₂", low: 95, high: 100, unit: "%", critLow: "<90", critHigh: "—" },
              { name: "Blood Glucose", low: 3.9, high: 7.8, unit: "mmol/L", critLow: "<2.8", critHigh: ">22.2" },
            ].map((row) => (
              <Table.Tr key={row.name}>
                <Table.Td><Text size="sm" fw={500}>{row.name}</Text></Table.Td>
                <Table.Td><Badge color="green" variant="light" size="sm">{row.low}–{row.high}</Badge></Table.Td>
                <Table.Td><Text size="xs" c="dimmed">{row.unit}</Text></Table.Td>
                <Table.Td><Text size="xs" c="red">{row.critLow}</Text></Table.Td>
                <Table.Td><Text size="xs" c="red">{row.critHigh}</Text></Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Card>
    </Stack>
  );
}
