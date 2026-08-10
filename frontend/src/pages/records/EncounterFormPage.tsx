import {
  Button,
  Card,
  Group,
  Select,
  Stack,
  Textarea,
  Title,
  Checkbox,
  SimpleGrid,
  Divider,
} from "@mantine/core";
import { useForm } from "@mantine/form";
import { notifications } from "@mantine/notifications";
import { IconCheck, IconStethoscope } from "@tabler/icons-react";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { createEncounter, createDiagnosis } from "@/api/endpoints";

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

const ENCOUNTER_TYPES = [
  { value: "OPD",  label: "Outpatient (OPD)" },
  { value: "IPD",  label: "Inpatient (IPD)" },
  { value: "EMRG", label: "Emergency" },
  { value: "FU",   label: "Follow-up" },
  { value: "TM",   label: "Telemedicine" },
];

const ICD10_DIAGNOSES = [
  { value: "B54", label: "B54 — Malaria, unspecified" },
  { value: "I10", label: "I10 — Essential (primary) hypertension" },
  { value: "A09", label: "A09 — Infectious gastroenteritis and colitis" },
  { value: "E11", label: "E11 — Type 2 diabetes mellitus" },
  { value: "J45", label: "J45 — Asthma" },
  { value: "A01", label: "A01 — Typhoid and paratyphoid fevers" },
  { value: "N39", label: "N39 — Urinary tract infection (UTI)" },
  { value: "J06", label: "J06 — Acute upper respiratory infections" },
];

export function EncounterFormPage() {
  const { nhid }  = useParams<{ nhid: string }>();
  const navigate  = useNavigate();
  const [loading, setLoading] = useState(false);
  const [icdCode, setIcdCode] = useState<string | null>(null);

  const form = useForm({
    initialValues: {
      encounter_type:  "OPD",
      chief_complaint: "",
      subjective: "",
      objective: "",
      assessment_notes: "",
      plan: "",
      is_walkin: false,
    },
    validate: {
      chief_complaint: (v) => (v.trim() ? null : "Chief complaint is required"),
      subjective: (v) => (v.trim() ? null : "Subjective clinical notes are required"),
    },
  });

  async function handleSubmit(values: typeof form.values) {
    setLoading(true);
    try {
      // 1. Compile SOAP fields into notes markdown block
      const soapNotes = `
### Subjective
${values.subjective}

### Objective
${values.objective || "Not recorded."}

### Assessment
${icdCode ? `ICD-10 Code: ${icdCode} — ${ICD10_DIAGNOSES.find(d => d.value === icdCode)?.label}` : ""}
${values.assessment_notes || "Not recorded."}

### Plan
${values.plan || "Not recorded."}
      `.trim();

      // 2. Submit Encounter
      const res = await createEncounter(nhid!, {
        encounter_type: values.encounter_type,
        chief_complaint: values.chief_complaint,
        notes: soapNotes,
      });

      const encounterId = res.data.id;

      // 3. Submit diagnosis if ICD-10 code is selected
      if (icdCode) {
        const icdLabel = ICD10_DIAGNOSES.find(d => d.value === icdCode)?.label || icdCode;
        await createDiagnosis(encounterId, {
          icd_code: icdCode,
          description: icdLabel.substring(icdLabel.indexOf("—") + 2),
          is_primary: true,
        });
      }

      notifications.show({
        color: "green",
        icon: <IconCheck />,
        title: "Encounter Created",
        message: values.is_walkin 
          ? "Walk-in consultation recorded & queued."
          : "Clinical encounter recorded successfully.",
      });

      navigate(`/encounters/${encounterId}`);
    } catch (err) {
      notifications.show({ color: "red", message: formatApiError(err, "Failed to save encounter SOAP note.") });
    } finally {
      setLoading(false);
    }
  }

  return (
    <Stack gap="lg">
      <Group justify="space-between">
        <Title order={2}>New SOAP Consultation</Title>
      </Group>

      <Card withBorder radius="md" padding="lg">
        <form onSubmit={form.onSubmit(handleSubmit)}>
          <Stack gap="md">
            <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="md">
              <Select
                label="Encounter Type"
                data={ENCOUNTER_TYPES}
                required
                {...form.getInputProps("encounter_type")}
              />
              <Group align="flex-end" h="100%" pb="sm">
                <Checkbox
                  label="Is walk-in patient"
                  {...form.getInputProps("is_walkin", { type: "checkbox" })}
                />
              </Group>
            </SimpleGrid>

            <Textarea
              label="Chief Complaint / Presenting Problem"
              placeholder="Describe the patient's main complaint…"
              required
              rows={2}
              {...form.getInputProps("chief_complaint")}
            />

            <Divider label="SOAP Notes" labelPosition="center" my="xs" />

            <Textarea
              label="Subjective (S)"
              placeholder="Patient symptoms, history of presenting illness, allergy details..."
              description="What the patient tells you."
              required
              rows={3}
              {...form.getInputProps("subjective")}
            />

            <Textarea
              label="Objective (O)"
              placeholder="Physical exam findings, vitals inspection, local symptoms observation..."
              description="What you observe and measure."
              rows={3}
              {...form.getInputProps("objective")}
            />

            <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="md">
              <Select
                label="Assessment (A) — ICD-10 Primary Code"
                placeholder="Search diagnostic code…"
                data={ICD10_DIAGNOSES}
                value={icdCode}
                onChange={setIcdCode}
                clearable
                searchable
              />
              <Textarea
                label="Clinical Assessment Notes"
                placeholder="Differential diagnoses, clinical impressions..."
                rows={2}
                {...form.getInputProps("assessment_notes")}
              />
            </SimpleGrid>

            <Textarea
              label="Plan (P)"
              placeholder="Treatment details, medication dosing prescriptions, lab orders requested, referrals, follow-up scheduling..."
              description="Steps to manage the patient."
              rows={3}
              {...form.getInputProps("plan")}
            />

            <Group justify="flex-end" mt="md">
              <Button variant="subtle" onClick={() => navigate(`/patients/${nhid}`)} color="gray">Cancel</Button>
              <Button
                type="submit"
                loading={loading}
                leftSection={<IconStethoscope size={16} />}
              >
                Create Encounter
              </Button>
            </Group>
          </Stack>
        </form>
      </Card>
    </Stack>
  );
}
