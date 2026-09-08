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
import { formatApiError } from "../../utils/formatApiError";
import { ConfidentialityLevel } from "@/types";
import { useAuth } from "@/auth/AuthProvider";

import { COMMON_ICD10_CODES, Icd10Option } from "@/constants/icd10Data";

const ENCOUNTER_TYPES = [
  { value: "OPD",  label: "Outpatient (OPD)" },
  { value: "IPD",  label: "Inpatient (IPD)" },
  { value: "EMRG", label: "Emergency" },
  { value: "FU",   label: "Follow-up" },
  { value: "TM",   label: "Telemedicine" },
];

export function EncounterFormPage() {
  const { nhid }  = useParams<{ nhid: string }>();
  const { user }  = useAuth();
  const navigate  = useNavigate();
  const [loading, setLoading] = useState(false);
  const [icdCode, setIcdCode] = useState<string | null>(null);
  const [icdOptions, setIcdOptions] = useState<Icd10Option[]>(COMMON_ICD10_CODES);

  const isDoctor = user?.role === "doctor";

  const form = useForm({
    initialValues: {
      encounter_type:  "OPD",
      confidentiality: "normal" as ConfidentialityLevel,
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
      const selectedOption = icdOptions.find((d) => d.value === icdCode);
      const optionLabel = selectedOption?.label || icdCode;

      // 1. Compile SOAP fields into notes markdown block
      const soapNotes = `
### Subjective
${values.subjective}

### Objective
${values.objective || "Not recorded."}

### Assessment
${(isDoctor && icdCode) ? `ICD-10 Code: ${icdCode} — ${optionLabel}` : ""}
${values.assessment_notes || "Not recorded."}

### Plan
${values.plan || "Not recorded."}
      `.trim();

      // 2. Submit Encounter
      const res = await createEncounter(nhid!, {
        encounter_type: values.encounter_type,
        chief_complaint: values.chief_complaint,
        notes: soapNotes,
        confidentiality: values.confidentiality,
      });

      const encounterId = res.data.id;

      // 3. Submit diagnosis if ICD-10 code is selected and author is doctor
      if (isDoctor && icdCode) {
        const description = selectedOption?.label?.includes("—")
          ? selectedOption.label.substring(selectedOption.label.indexOf("—") + 2).trim()
          : (values.assessment_notes?.trim() || selectedOption?.label || `Diagnosis ${icdCode}`);

        await createDiagnosis(encounterId, {
          icd_code: icdCode,
          description,
          is_primary: true,
          confidentiality: values.confidentiality,
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
            <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="md">
              <Select
                label="Encounter Type"
                data={ENCOUNTER_TYPES}
                required
                {...form.getInputProps("encounter_type")}
              />
              <Select
                label="Confidentiality Tier"
                description="Statutory tier under Act 843"
                data={[
                  { value: "normal", label: "Normal (Standard Care)" },
                  { value: "restricted", label: "Restricted (Mental/HIV)" },
                  { value: "very_restricted", label: "Very Restricted (VIP)" },
                ]}
                required
                {...form.getInputProps("confidentiality")}
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

            {isDoctor ? (
              <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="md">
                <Select
                  label="Assessment (A) — ICD-10 Primary Code"
                  placeholder="Search code or condition, or type custom code…"
                  data={icdOptions}
                  value={icdCode}
                  onChange={setIcdCode}
                  onSearchChange={(search) => {
                    const trimmed = search.trim().toUpperCase();
                    if (trimmed && !icdOptions.some((d) => d.value.toLowerCase() === trimmed.toLowerCase())) {
                      setIcdOptions([
                        { value: trimmed, label: `${trimmed} (Custom ICD-10 Code)`, category: "Custom" },
                        ...COMMON_ICD10_CODES,
                      ]);
                    }
                  }}
                  clearable
                  searchable
                  nothingFoundMessage="Type code to add custom diagnosis"
                />
                <Textarea
                  label="Clinical Assessment Notes"
                  placeholder="Differential diagnoses, clinical impressions..."
                  rows={2}
                  {...form.getInputProps("assessment_notes")}
                />
              </SimpleGrid>
            ) : (
              <Textarea
                label="Assessment (A) — Nursing Observations & Impressions"
                placeholder="Nursing impressions, symptom progression, care observations (definitive ICD-10 coding is physician-only)..."
                description="Nursing assessments and clinical observations."
                rows={3}
                {...form.getInputProps("assessment_notes")}
              />
            )}

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
