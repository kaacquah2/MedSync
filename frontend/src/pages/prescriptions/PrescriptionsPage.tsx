import {
  Autocomplete,
  Badge,
  Box,
  Button,
  Card,
  Divider,
  Group,
  NumberInput,
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
  Alert,
  Modal,
} from "@mantine/core";
import { useForm } from "@mantine/form";
import { notifications } from "@mantine/notifications";
import {
  IconCheck,
  IconPill,
  IconSearch,
  IconAlertTriangle,
  IconPrinter,
} from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import dayjs from "dayjs";
import { useState, useMemo } from "react";
import { createPrescription, fetchPatientEncounters, searchPatients, fetchPatient } from "@/api/endpoints";
import { useAuth } from "@/auth/AuthProvider";
import { checkAllergyConflicts } from "@/utils/allergyChecker";
import { useIsPrinting } from "@/utils/useIsPrinting";

// ── Ghana Essential Medicines List (common subset for autocomplete) ────────────
const GHANA_EML_DRUGS = [
  "Amoxicillin 250mg", "Amoxicillin 500mg", "Amoxicillin-Clavulanate 625mg",
  "Ampicillin 250mg", "Ampicillin 500mg", "Benzylpenicillin 600mg",
  "Chloramphenicol 250mg", "Ciprofloxacin 250mg", "Ciprofloxacin 500mg",
  "Co-trimoxazole 480mg", "Doxycycline 100mg", "Erythromycin 250mg",
  "Gentamicin 80mg/2ml", "Metronidazole 200mg", "Metronidazole 400mg",
  "Metronidazole 500mg/100ml IV", "Ceftriaxone 1g IV", "Cefuroxime 250mg",
  "Clindamycin 150mg", "Fluconazole 150mg", "Griseofulvin 125mg",
  "Artemether-Lumefantrine 20/120mg", "Artesunate 50mg", "Chloroquine 150mg",
  "Quinine 300mg", "Primaquine 7.5mg",
  "Amlodipine 5mg", "Amlodipine 10mg", "Atenolol 50mg", "Atenolol 100mg",
  "Captopril 25mg", "Enalapril 5mg", "Enalapril 10mg",
  "Furosemide 40mg", "Hydrochlorothiazide 25mg", "Lisinopril 5mg",
  "Nifedipine 10mg SR", "Propranolol 40mg", "Spironolactone 25mg",
  "Methyldopa 250mg",
  "Aspirin 75mg", "Aspirin 300mg", "Clopidogrel 75mg",
  "Digoxin 62.5mcg", "Digoxin 250mcg",
  "Metformin 500mg", "Metformin 850mg", "Glibenclamide 5mg",
  "Insulin Actrapid 100IU/ml", "Insulin Mixtard 30/70",
  "Prednisolone 5mg", "Prednisolone 25mg", "Dexamethasone 4mg",
  "Hydrocortisone 100mg IV",
  "Paracetamol 500mg", "Ibuprofen 200mg", "Ibuprofen 400mg",
  "Diclofenac 50mg", "Tramadol 50mg", "Morphine 10mg",
  "Codeine 30mg",
  "Omeprazole 20mg", "Omeprazole 40mg", "Ranitidine 150mg",
  "Antacid (Magnesium hydroxide)", "Metoclopramide 10mg",
  "Oral Rehydration Salts (ORS)", "Zinc Sulphate 20mg",
  "Ferrous Sulphate 200mg", "Folic Acid 5mg", "Vitamin A 200,000IU",
  "Multivitamin (standard)",
  "Salbutamol 100mcg inhaler", "Beclomethasone 100mcg inhaler",
  "Aminophylline 250mg", "Ipratropium 20mcg inhaler",
  "Diazepam 5mg", "Diazepam 10mg/2ml IV", "Phenobarbitone 30mg",
  "Phenytoin 100mg", "Carbamazepine 200mg", "Sodium Valproate 200mg",
  "Haloperidol 5mg", "Chlorpromazine 100mg", "Risperidone 2mg",
  "Amitriptyline 25mg", "Fluoxetine 20mg",
];

const ROUTES = [
  { value: "oral", label: "Oral (PO)" },
  { value: "iv", label: "Intravenous (IV)" },
  { value: "im", label: "Intramuscular (IM)" },
  { value: "sc", label: "Subcutaneous (SC)" },
  { value: "topical", label: "Topical" },
  { value: "inhaled", label: "Inhaled" },
  { value: "sublingual", label: "Sublingual (SL)" },
  { value: "rectal", label: "Rectal (PR)" },
  { value: "nasal", label: "Intranasal" },
  { value: "optic", label: "Ophthalmic" },
];

const FREQUENCIES = [
  { value: "once_daily", label: "Once daily (OD)", multiplier: 1 },
  { value: "twice_daily", label: "Twice daily (BD)", multiplier: 2 },
  { value: "three_daily", label: "Three times daily (TDS)", multiplier: 3 },
  { value: "four_daily", label: "Four times daily (QDS)", multiplier: 4 },
  { value: "every_8h", label: "Every 8 hours", multiplier: 3 },
  { value: "every_6h", label: "Every 6 hours", multiplier: 4 },
  { value: "every_4h", label: "Every 4 hours", multiplier: 6 },
  { value: "when_required", label: "When required (PRN)", multiplier: 1 },
  { value: "once_only", label: "Once only (stat)", multiplier: 1 },
  { value: "weekly", label: "Weekly", multiplier: 0.14 },
  { value: "at_night", label: "At night (nocte)", multiplier: 1 },
];

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

export function PrescriptionsPage() {
  const qc = useQueryClient();
  const { user } = useAuth();
  const [patientSearch, setPatientSearch] = useState("");
  const [selectedNhid, setSelectedNhid] = useState<string | null>(null);
  const [selectedEncounterId, setSelectedEncounterId] = useState<number | null>(null);
  const { isPrinting, triggerPrint } = useIsPrinting();

  // Patient search
  const { data: searchData, isLoading: searching } = useQuery({
    queryKey: ["rx-patient-search", patientSearch],
    queryFn: () => searchPatients(patientSearch).then((r) => r.data),
    enabled: patientSearch.length >= 2,
    staleTime: 10_000,
  });

  const patientOptions = searchData?.results.map((p) => ({
    value: p.universal_id,
    label: `${p.full_name} — ${p.universal_id}`,
  })) ?? [];

  // Patient details to fetch allergies/alerts
  const { data: activePatient } = useQuery({
    queryKey: ["rx-patient-details", selectedNhid],
    queryFn: () => fetchPatient(selectedNhid!).then((r) => r.data),
    enabled: !!selectedNhid,
  });

  // Encounters for selected patient
  const { data: encounters, isLoading: loadingEnc } = useQuery({
    queryKey: ["rx-encounters", selectedNhid],
    queryFn: () => fetchPatientEncounters(selectedNhid!).then((r) => r.data),
    enabled: !!selectedNhid,
  });

  const encounterOptions = (encounters ?? []).map((e) => ({
    value: String(e.id),
    label: `#${e.id} · ${e.encounter_type_display} · ${dayjs(e.created_at).format("DD MMM YYYY")}`,
  }));

  const form = useForm({
    initialValues: {
      drug_name: "",
      dosage: "",
      route: "",
      frequency: "",
      duration_days: 7 as number,
      instructions: "",
      rxnorm_code: "",
    },
    validate: {
      drug_name: (v) => (v.trim() ? null : "Drug name required"),
      dosage:    (v) => (v.trim() ? null : "Dosage required"),
      route:     (v) => (v ? null : "Route required"),
      frequency: (v) => (v ? null : "Frequency required"),
    },
  });

  // 1. Auto-calculate total quantity
  const totalQuantity = useMemo(() => {
    const freqObj = FREQUENCIES.find((f) => f.value === form.values.frequency);
    if (!freqObj || !form.values.duration_days) return 0;
    return Math.ceil(freqObj.multiplier * Number(form.values.duration_days));
  }, [form.values.frequency, form.values.duration_days]);

  // 2. Allergy contraindication checker
  const allergyConflicts = useMemo(() => {
    if (!activePatient || !form.values.drug_name) return [];
    return checkAllergyConflicts(activePatient.alerts, form.values.drug_name);
  }, [activePatient, form.values.drug_name]);

  const [overrideModalOpen, setOverrideModalOpen] = useState(false);
  const [overrideReason, setOverrideReason] = useState("");
  const [overrideError, setOverrideError] = useState("");
  const [pendingValues, setPendingValues] = useState<typeof form.values | null>(null);

  const mutation = useMutation({
    mutationFn: ({ values, overrideReason }: { values: typeof form.values; overrideReason?: string }) => {
      const encId = selectedEncounterId ?? encounters?.[0]?.id;
      if (!encId) throw new Error("No encounter selected");
      return createPrescription(encId, {
        drug_name:    values.drug_name,
        dosage:       `${values.dosage} ${values.route}`,
        frequency:    `${FREQUENCIES.find(f=>f.value===values.frequency)?.label ?? values.frequency}${values.duration_days ? ` for ${values.duration_days} days` : ""}`,
        instructions: `${values.instructions || ""}${totalQuantity ? ` (Total Quantity: ${totalQuantity})` : ""}`,
        rxnorm_code:  values.rxnorm_code || undefined,
        allergy_override_reason: overrideReason || undefined,
      });
    },
    onSuccess: () => {
      notifications.show({ color: "green", icon: <IconCheck />, message: "Prescription saved successfully." });
      form.reset();
      setOverrideModalOpen(false);
      setOverrideReason("");
      setOverrideError("");
      setPendingValues(null);
      qc.invalidateQueries({ queryKey: ["rx-encounters", selectedNhid] });
    },
    onError: (e: unknown) => {
      const respData = (e as { response?: { data?: { error?: string; detail?: string } } })?.response?.data;
      if (respData?.error === "ALLERGY_CONFLICT") {
        setOverrideError(respData.detail || "Documented allergy conflict. Written clinical override justification is required.");
        setOverrideModalOpen(true);
      } else {
        notifications.show({
          color: "red",
          message: formatApiError(e, "Failed to save prescription."),
        });
      }
    },
  });

  const handleFormSubmit = (v: typeof form.values) => {
    if (allergyConflicts.length > 0) {
      setPendingValues(v);
      setOverrideReason("");
      setOverrideError("");
      setOverrideModalOpen(true);
      return;
    }
    mutation.mutate({ values: v });
  };

  const handleConfirmOverride = () => {
    if (!overrideReason.trim() || overrideReason.trim().length < 10) {
      setOverrideError("Mandatory clinical override justification must be at least 10 characters.");
      return;
    }
    if (!pendingValues) return;
    mutation.mutate({ values: pendingValues, overrideReason: overrideReason.trim() });
  };

  return (
    <Stack gap="lg">
      {/* Header */}
      <Group justify="space-between" align="center" className="no-print">
        <Group gap="xs">
          <ThemeIcon size={36} color="violet" variant="light" radius="md">
            <IconPill size={20} />
          </ThemeIcon>
          <Box>
            <Title order={2} style={{ fontSize: "20px", fontWeight: 500 }}>Prescription Writer</Title>
            <Text size="xs" c="dimmed">Ghana Essential Medicines List · ICD-compliant dosing</Text>
          </Box>
        </Group>
        {selectedNhid && (
          <Button
            leftSection={<IconPrinter size={16} />}
            variant="outline"
            color="violet"
            onClick={triggerPrint}
          >
            Print Prescription
          </Button>
        )}
      </Group>

      <SimpleGrid cols={{ base: 1, lg: 2 }} spacing="lg" className="no-print">
        {/* Left — form */}
        <Card withBorder radius="md" p="lg">
          <Text fw={600} size="sm" tt="uppercase" c="dimmed" mb="md">New Prescription</Text>

          {/* Step 1: Patient + encounter */}
          <Stack gap="sm" mb="md">
            <Select
              label="Patient"
              placeholder="Search by name or NHID…"
              leftSection={<IconSearch size={16} />}
              searchable
              data={patientOptions}
              onSearchChange={setPatientSearch}
              value={selectedNhid}
              onChange={(v) => { setSelectedNhid(v); setSelectedEncounterId(null); }}
              nothingFoundMessage={patientSearch.length < 2 ? "Type at least 2 characters" : searching ? "Searching…" : "No patients found"}
            />

            {selectedNhid && (
              <Select
                label="Encounter"
                placeholder={loadingEnc ? "Loading…" : "Select encounter"}
                data={encounterOptions}
                value={selectedEncounterId ? String(selectedEncounterId) : null}
                onChange={(v) => setSelectedEncounterId(v ? Number(v) : null)}
                disabled={loadingEnc || !encounterOptions.length}
                description={!encounterOptions.length && !loadingEnc ? "No encounters found for this patient" : undefined}
              />
            )}
          </Stack>

          <Divider mb="md" />

          {/* Allergy warning banner */}
          {allergyConflicts.length > 0 && (
            <Alert
              icon={<IconAlertTriangle size={18} />}
              color="red"
              title="Contraindicated Allergy Alert"
              mb="md"
            >
              <Stack gap={4}>
                {allergyConflicts.map((c) => (
                  <Text size="sm" key={c.allergyId}>
                    <strong>{activePatient?.full_name}</strong> has a documented allergy to{" "}
                    <strong>{c.allergyLabel}</strong> ({c.severity}). {c.message}
                    {c.reaction ? ` Recorded reaction: ${c.reaction}.` : ""}
                  </Text>
                ))}
                <Text size="xs" fw={700} mt={4} c="red.9">
                  Submission is blocked: an explicit clinical override justification is required to prescribe this medication.
                </Text>
              </Stack>
            </Alert>
          )}

          {/* Step 2: Drug */}
          <form onSubmit={form.onSubmit(handleFormSubmit)}>
            <Stack gap="sm">
              <Autocomplete
                label="Drug name"
                placeholder="e.g. Amoxicillin 500mg"
                data={GHANA_EML_DRUGS}
                limit={8}
                required
                {...form.getInputProps("drug_name")}
              />

              <SimpleGrid cols={2} spacing="sm">
                <TextInput
                  label="Strength / Dosage"
                  placeholder="e.g. 500mg"
                  required
                  {...form.getInputProps("dosage")}
                />
                <Select
                  label="Route"
                  placeholder="Select route"
                  data={ROUTES}
                  required
                  {...form.getInputProps("route")}
                />
              </SimpleGrid>

              <SimpleGrid cols={2} spacing="sm">
                <Select
                  label="Frequency"
                  placeholder="Select frequency"
                  data={FREQUENCIES}
                  required
                  {...form.getInputProps("frequency")}
                />
                <NumberInput
                  label="Duration (days)"
                  placeholder="e.g. 7"
                  min={1}
                  max={365}
                  {...form.getInputProps("duration_days")}
                />
              </SimpleGrid>

              {totalQuantity > 0 && (
                <Text size="xs" fw={700} c="medsync">
                  Estimated total quantity: {totalQuantity} units
                </Text>
              )}

              <Textarea
                label="Additional instructions"
                placeholder="e.g. Take with food. Avoid alcohol."
                rows={2}
                {...form.getInputProps("instructions")}
              />

              <TextInput
                label="RxNorm code"
                placeholder="Optional"
                {...form.getInputProps("rxnorm_code")}
              />

              <Group justify="flex-end" mt="xs">
                <Button variant="subtle" type="button" onClick={() => form.reset()} color="gray">
                  Clear
                </Button>
                <Button
                  type="submit"
                  color={allergyConflicts.length > 0 ? "red" : "violet"}
                  leftSection={allergyConflicts.length > 0 ? <IconAlertTriangle size={16} /> : <IconPill size={16} />}
                  loading={mutation.isPending}
                  disabled={!selectedNhid}
                >
                  {allergyConflicts.length > 0 ? "Review Allergy Override & Prescribe" : "Save Prescription"}
                </Button>
              </Group>
            </Stack>
          </form>
        </Card>

        {/* Right — recent prescriptions for patient */}
        <Card withBorder radius="md" p="lg">
          <Text fw={600} size="sm" tt="uppercase" c="dimmed" mb="md">
            {selectedNhid ? `Prescriptions for patient` : "Select a patient to view prescriptions"}
          </Text>

          {!selectedNhid ? (
            <Box ta="center" py="xl">
              <Text c="dimmed" size="sm">No patient selected.</Text>
            </Box>
          ) : loadingEnc ? (
            <Stack gap="xs">
              {[1, 2, 3].map((i) => <Skeleton key={i} height={48} radius="sm" />)}
            </Stack>
          ) : (
            <RecentRxTable encounters={encounters ?? []} />
          )}
        </Card>
      </SimpleGrid>

      {/* ── Print Friendly Output ─────────────────────────────────────────── */}
      {isPrinting && selectedNhid && activePatient && (
        <Card className="print-only" p="xl" style={{ border: "2px solid #ccc", minHeight: "600px" }}>
          <Stack gap="xl">
            {/* Hospital Header */}
            <Group justify="space-between">
              <Box>
                <Title order={3}>{user?.hospital?.name || "—"}</Title>
                <Text size="xs" c="dimmed">Hospital ID: {user?.hospital?.code || "—"}</Text>
              </Box>
              <Badge color="violet" size="lg">Rx PRESCRIPTION</Badge>
            </Group>
            <Divider />

            {/* Patient & Doctor demographics */}
            <SimpleGrid cols={2} spacing="md">
              <Box>
                <Text size="xs" c="dimmed">PATIENT DETAILS</Text>
                <Text fw={700} size="md">{activePatient.full_name}</Text>
                <Text size="xs">NHID: {activePatient.universal_id}</Text>
                <Text size="xs">DOB: {activePatient.date_of_birth} ({activePatient.sex_display})</Text>
              </Box>
              <Box style={{ textAlign: "right" }}>
                <Text size="xs" c="dimmed">PRESCRIBING CLINICIAN</Text>
                <Text fw={700} size="md">Dr. {user?.first_name} {user?.last_name || user?.username}</Text>
                <Text size="xs">Date: {dayjs().format("DD MMM YYYY")}</Text>
              </Box>
            </SimpleGrid>

            <Divider />

            {/* Prescribed Drug Details */}
            <Box style={{ minHeight: 250 }}>
              <Text size="xs" c="dimmed" mb="md">PRESCRIBED MEDICINES</Text>
              <Table striped>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>Drug Name</Table.Th>
                    <Table.Th>Dosage / Strength</Table.Th>
                    <Table.Th>Frequency</Table.Th>
                    <Table.Th>Quantity</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {form.values.drug_name ? (
                    <Table.Tr>
                      <Table.Td fw={700}>{form.values.drug_name}</Table.Td>
                      <Table.Td>{form.values.dosage} {form.values.route}</Table.Td>
                      <Table.Td>{FREQUENCIES.find(f => f.value === form.values.frequency)?.label || form.values.frequency} for {form.values.duration_days} days</Table.Td>
                      <Table.Td fw={700}>{totalQuantity} units</Table.Td>
                    </Table.Tr>
                  ) : (
                    <Table.Tr>
                      <Table.Td colSpan={4} style={{ textAlign: "center", color: "var(--text-muted)" }}>
                        Complete the prescription form before printing.
                      </Table.Td>
                    </Table.Tr>
                  )}
                </Table.Tbody>
              </Table>
              {form.values.instructions && (
                <Box mt="md">
                  <Text size="xs" c="dimmed">INSTRUCTIONS FOR PATIENT:</Text>
                  <Text size="sm">{form.values.instructions}</Text>
                </Box>
              )}
            </Box>

            {/* Signature Block */}
            <Group justify="space-between" mt="xl" pt="xl">
              <Box>
                <Text size="xs" c="dimmed">AUDIT REFERENCE</Text>
                <Text size="xs" ff="monospace" style={{ fontSize: 9 }}>
                  mEd-{dayjs().format("YYYYMMDD")}-{activePatient?.universal_id || "—"}
                </Text>
              </Box>
              <Box style={{ borderTop: "1px solid var(--border)", width: "200px", textAlign: "center", paddingTop: 8 }}>
                <Text size="xs" c="dimmed">CLINICIAN SIGNATURE & STAMP</Text>
              </Box>
            </Group>
          </Stack>
        </Card>
      )}

      {/* Clinical Allergy Override Modal */}
      <Modal
        opened={overrideModalOpen}
        onClose={() => setOverrideModalOpen(false)}
        title={
          <Group gap="xs">
            <ThemeIcon color="red" variant="light" size="md">
              <IconAlertTriangle size={18} />
            </ThemeIcon>
            <Text fw={700} c="red.8">Clinical Allergy Override Required</Text>
          </Group>
        }
        centered
        size="lg"
      >
        <Stack gap="md">
          <Alert color="red" icon={<IconAlertTriangle size={18} />} title="Contraindicated Medication Warning">
            <Text size="sm">
              You are attempting to prescribe <strong>{pendingValues?.drug_name || form.values.drug_name}</strong> to{" "}
              <strong>{activePatient?.full_name}</strong> ({activePatient?.universal_id}), who has active documented allergies:
            </Text>
            <Stack gap={4} mt="xs">
              {allergyConflicts.map((c) => (
                <Text size="xs" key={c.allergyId}>
                  • <strong>{c.allergyLabel}</strong> (Severity: <strong>{c.severity}</strong>)
                  {c.reaction ? ` — Reaction: ${c.reaction}` : ""}
                </Text>
              ))}
            </Stack>
          </Alert>

          <Text size="xs" c="dimmed">
            Clinical safety protocol requires mandatory written clinical justification before overriding a documented allergy.
            This override, along with your clinical rationale, will be permanently recorded in the immutable audit log under your clinician credentials.
          </Text>

          <Textarea
            label="Clinical Justification for Override"
            placeholder="e.g. Desensitization protocol completed under immunology guidance; ICU monitored; therapeutic benefits outweigh risks."
            minRows={3}
            required
            value={overrideReason}
            onChange={(e) => {
              setOverrideReason(e.currentTarget.value);
              if (overrideError) setOverrideError("");
            }}
            error={overrideError}
          />

          <Group justify="flex-end" mt="xs">
            <Button variant="subtle" color="gray" onClick={() => setOverrideModalOpen(false)}>
              Cancel / Change Drug
            </Button>
            <Button
              color="red"
              leftSection={<IconAlertTriangle size={16} />}
              loading={mutation.isPending}
              onClick={handleConfirmOverride}
            >
              Confirm Override & Prescribe
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Stack>
  );
}

function RecentRxTable({ encounters }: { encounters: { id: number; prescriptions?: { id: number; drug_name: string; dosage: string; frequency: string; instructions?: string }[] }[] }) {
  const allRx = encounters.flatMap((e) => (e.prescriptions ?? []).map((rx) => ({ ...rx, enc_id: e.id })));

  if (!allRx.length) {
    return (
      <Box ta="center" py="xl">
        <Text c="dimmed" size="sm">No prescriptions recorded for this patient.</Text>
      </Box>
    );
  }

  return (
    <Table.ScrollContainer minWidth={350}>
      <Table striped highlightOnHover>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Drug</Table.Th>
            <Table.Th>Dosage</Table.Th>
            <Table.Th>Frequency</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {allRx.map((rx) => (
            <Table.Tr key={rx.id}>
              <Table.Td><Text fw={600} size="sm">{rx.drug_name}</Text></Table.Td>
              <Table.Td><Badge variant="light" color="violet" size="sm">{rx.dosage}</Badge></Table.Td>
              <Table.Td><Text size="sm">{rx.frequency}</Text></Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </Table.ScrollContainer>
  );
}
