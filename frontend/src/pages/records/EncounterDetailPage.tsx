import {
  Alert,
  Badge,
  Box,
  Button,
  Card,
  Center,
  Group,
  Modal,
  Select,
  Skeleton,
  Stack,
  Table,
  Text,
  Textarea,
  TextInput,
  ThemeIcon,
  Title,
} from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import { useForm } from "@mantine/form";
import { notifications } from "@mantine/notifications";
import {
  IconArrowLeftRight,
  IconCheck,
  IconFlask,
  IconPill,
  IconPlus,
  IconStethoscope,
} from "@tabler/icons-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import dayjs from "dayjs";
import { Link, useParams } from "react-router-dom";
import { createDiagnosis, createLabResult, createPrescription, fetchEncounter } from "@/api/endpoints";

// ICD-10 common codes autocomplete list
const ICD10_CODES = [
  { value: "J00", label: "J00 — Common cold" },
  { value: "J18.9", label: "J18.9 — Pneumonia, unspecified" },
  { value: "I10", label: "I10 — Essential hypertension" },
  { value: "E11.9", label: "E11.9 — Type 2 diabetes, without complications" },
  { value: "A09", label: "A09 — Diarrhoea and gastroenteritis" },
  { value: "B54", label: "B54 — Unspecified malaria" },
  { value: "J06.9", label: "J06.9 — Acute URTI, unspecified" },
  { value: "K29.7", label: "K29.7 — Gastritis, unspecified" },
  { value: "M54.5", label: "M54.5 — Low back pain" },
  { value: "R50.9", label: "R50.9 — Fever, unspecified" },
];

export function EncounterDetailPage() {
  const { id }     = useParams<{ id: string }>();
  const qc         = useQueryClient();

  const { data: encounter, isLoading } = useQuery({
    queryKey: ["encounter", id],
    queryFn:  () => fetchEncounter(Number(id)).then((r) => r.data),
    enabled:  !!id,
  });

  const [diagOpen, { open: openDiag, close: closeDiag }]   = useDisclosure(false);
  const [rxOpen,   { open: openRx,   close: closeRx   }]   = useDisclosure(false);
  const [labOpen,  { open: openLab,  close: closeLab  }]   = useDisclosure(false);

  const diagForm = useForm({
    initialValues: { icd_code: "", snomed_code: "", description: "", is_primary: true },
    validate: {
      description: (v) => (v.trim() ? null : "Diagnosis description is required"),
    },
  });
  const rxForm = useForm({
    initialValues: { drug_name: "", rxnorm_code: "", dosage: "", frequency: "", instructions: "" },
    validate: {
      drug_name:  (v) => (v.trim() ? null : "Drug name is required"),
      dosage:     (v) => (v.trim() ? null : "Dosage is required (e.g. 500 mg)"),
      frequency:  (v) => (v.trim() ? null : "Frequency is required (e.g. twice daily)"),
    },
  });
  const labForm = useForm({
    initialValues: { test_name: "", loinc_code: "", result_value: "", reference_range: "", is_abnormal: false },
    validate: {
      test_name:    (v) => (v.trim() ? null : "Test name is required"),
      result_value: (v) => (v.trim() ? null : "Result value is required"),
    },
  });

  async function submitDiagnosis(values: typeof diagForm.values) {
    try {
      await createDiagnosis(Number(id), values);
      notifications.show({ color: "green", icon: <IconCheck />, message: "Diagnosis added." });
      qc.invalidateQueries({ queryKey: ["encounter", id] });
      closeDiag(); diagForm.reset();
    } catch {
      notifications.show({ color: "red", message: "Failed to save diagnosis. Please try again." });
    }
  }

  async function submitRx(values: typeof rxForm.values) {
    try {
      await createPrescription(Number(id), values);
      notifications.show({ color: "green", icon: <IconCheck />, message: "Prescription added." });
      qc.invalidateQueries({ queryKey: ["encounter", id] });
      closeRx(); rxForm.reset();
    } catch {
      notifications.show({ color: "red", message: "Failed to save prescription. Please try again." });
    }
  }

  async function submitLab(values: typeof labForm.values) {
    try {
      await createLabResult(Number(id), values);
      notifications.show({ color: "green", icon: <IconCheck />, message: "Lab result added." });
      qc.invalidateQueries({ queryKey: ["encounter", id] });
      closeLab(); labForm.reset();
    } catch {
      notifications.show({ color: "red", message: "Failed to save lab result. Please try again." });
    }
  }

  if (isLoading) {
    return (
      <Stack gap="md">
        <Skeleton height={120} radius="md" />
        <Skeleton height={40} radius="sm" />
        <Skeleton height={200} radius="md" />
      </Stack>
    );
  }
  if (!encounter) {
    return (
      <Center h={300}>
        <Stack align="center" gap="xs">
          <ThemeIcon size={56} color="danger" variant="light" radius="xl">
            <IconStethoscope size={32} />
          </ThemeIcon>
          <Text c="dimmed" fw={500}>Encounter not found.</Text>
        </Stack>
      </Center>
    );
  }

  const canDiagnose  = encounter.can_diagnose  ?? false;
  const canPrescribe = encounter.can_prescribe ?? false;
  const canLab       = encounter.can_add_lab   ?? false;

  return (
    <Stack gap="lg">
      {encounter.is_cross_hospital && (
        <Alert color="yellow" icon={<IconArrowLeftRight />} title="Cross-hospital encounter">
          This encounter was created at {encounter.created_at_hospital?.name}.
        </Alert>
      )}

      {/* Encounter header */}
      <Card withBorder radius="md" padding="lg">
        <Group justify="space-between" mb="md">
          <Group>
            <ThemeIcon size={44} color="medsync" variant="light" radius="md">
              <IconStethoscope size={24} />
            </ThemeIcon>
            <Box>
              <Group gap="xs">
                <Badge size="lg" variant="filled">{encounter.encounter_type_display}</Badge>
                {encounter.is_cross_hospital && <Badge color="yellow" size="sm">External</Badge>}
              </Group>
              <Text size="sm" c="dimmed" mt={4}>
                {encounter.created_by?.full_name} · {encounter.created_at_hospital?.name} · {dayjs(encounter.created_at).format("DD MMM YYYY, HH:mm")}
              </Text>
            </Box>
          </Group>
          <Button component={Link} to={`/patients/${encounter.patient_nhid}`} variant="light" size="sm">
            ← Back to Patient
          </Button>
        </Group>

        <Box>
          <Text size="sm" fw={700} c="dimmed" tt="uppercase" mb={4}>Chief Complaint</Text>
          <Text>{encounter.chief_complaint}</Text>
          {encounter.notes && (
            <>
              <Text size="sm" fw={700} c="dimmed" tt="uppercase" mt="md" mb={4}>Clinical Notes</Text>
              <Text style={{ whiteSpace: "pre-wrap" }}>{encounter.notes}</Text>
            </>
          )}
        </Box>
      </Card>

      {/* Actions */}
      <Group>
        {canDiagnose && (
          <Button leftSection={<IconPlus size={16} />} variant="light" onClick={openDiag}>Add Diagnosis</Button>
        )}
        {canPrescribe && (
          <Button leftSection={<IconPill size={16} />} variant="light" color="violet" onClick={openRx}>Prescribe</Button>
        )}
        {canLab && (
          <Button leftSection={<IconFlask size={16} />} variant="light" color="clinical" onClick={openLab}>Add Lab Result</Button>
        )}
      </Group>

      {/* Diagnoses */}
      <Section title="Diagnoses" count={encounter.diagnoses.length} color="blue">
        {encounter.diagnoses.length === 0 ? (
          <Text c="dimmed" size="sm">No diagnoses recorded.</Text>
        ) : (
          <Table striped withTableBorder withColumnBorders>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>ICD-10</Table.Th>
                <Table.Th>Description</Table.Th>
                <Table.Th>Primary</Table.Th>
                <Table.Th>By</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {encounter.diagnoses.map((d) => (
                <Table.Tr key={d.id}>
                  <Table.Td><Badge variant="light" ff="monospace">{d.icd_code || "—"}</Badge></Table.Td>
                  <Table.Td>{d.description}</Table.Td>
                  <Table.Td>{d.is_primary ? <Badge color="green" size="sm">Primary</Badge> : "—"}</Table.Td>
                  <Table.Td><Text size="sm">{d.created_by?.full_name ?? "—"}</Text></Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        )}
      </Section>

      {/* Prescriptions */}
      <Section title="Prescriptions" count={encounter.prescriptions.length} color="violet">
        {encounter.prescriptions.length === 0 ? (
          <Text c="dimmed" size="sm">No prescriptions recorded.</Text>
        ) : (
          <Table striped withTableBorder withColumnBorders>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Drug</Table.Th>
                <Table.Th>Dosage</Table.Th>
                <Table.Th>Frequency</Table.Th>
                <Table.Th>Instructions</Table.Th>
                <Table.Th>By</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {encounter.prescriptions.map((rx) => (
                <Table.Tr key={rx.id}>
                  <Table.Td><Text fw={600}>{rx.drug_name}</Text></Table.Td>
                  <Table.Td>{rx.dosage}</Table.Td>
                  <Table.Td>{rx.frequency}</Table.Td>
                  <Table.Td>{rx.instructions || "—"}</Table.Td>
                  <Table.Td>{rx.created_by?.full_name ?? "—"}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        )}
      </Section>

      {/* Lab results */}
      <Section title="Lab Results" count={encounter.lab_results.length} color="teal">
        {encounter.lab_results.length === 0 ? (
          <Text c="dimmed" size="sm">No lab results recorded.</Text>
        ) : (
          <Table striped withTableBorder withColumnBorders>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Test</Table.Th>
                <Table.Th>LOINC</Table.Th>
                <Table.Th>Result</Table.Th>
                <Table.Th>Reference Range</Table.Th>
                <Table.Th>Status</Table.Th>
                <Table.Th>Performed</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {encounter.lab_results.map((lab) => (
                <Table.Tr key={lab.id} bg={lab.is_abnormal ? "red.0" : undefined}>
                  <Table.Td><Text fw={600}>{lab.test_name}</Text></Table.Td>
                  <Table.Td><Badge variant="light" size="sm" ff="monospace">{lab.loinc_code || "—"}</Badge></Table.Td>
                  <Table.Td>{lab.result_value}</Table.Td>
                  <Table.Td>{lab.reference_range || "—"}</Table.Td>
                  <Table.Td>
                    <Badge color={lab.is_abnormal ? "danger" : "clinical"} variant="light">
                      {lab.is_abnormal ? "Abnormal" : "Normal"}
                    </Badge>
                  </Table.Td>
                  <Table.Td>{lab.performed_at ? dayjs(lab.performed_at).format("DD MMM YYYY") : "—"}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        )}
      </Section>

      {/* Modals */}
      <Modal opened={diagOpen} onClose={closeDiag} title="Add Diagnosis" centered>
        <form onSubmit={diagForm.onSubmit(submitDiagnosis)}>
          <Stack>
            <Select
              label="ICD-10 Code"
              data={ICD10_CODES}
              searchable
              clearable
              {...diagForm.getInputProps("icd_code")}
            />
            <TextInput label="SNOMED CT Code" placeholder="Optional" {...diagForm.getInputProps("snomed_code")} />
            <Textarea label="Description" required rows={3} {...diagForm.getInputProps("description")} />
            <Group justify="flex-end">
              <Button variant="subtle" onClick={closeDiag}>Cancel</Button>
              <Button type="submit" leftSection={<IconCheck size={16} />}>Save Diagnosis</Button>
            </Group>
          </Stack>
        </form>
      </Modal>

      <Modal opened={rxOpen} onClose={closeRx} title="Add Prescription" centered>
        <form onSubmit={rxForm.onSubmit(submitRx)}>
          <Stack>
            <TextInput label="Drug / Medication Name" required {...rxForm.getInputProps("drug_name")} />
            <TextInput label="RxNorm Code" placeholder="Optional" {...rxForm.getInputProps("rxnorm_code")} />
            <TextInput label="Dosage & Route" placeholder="e.g. 500mg oral" required {...rxForm.getInputProps("dosage")} />
            <TextInput label="Frequency / Duration" placeholder="e.g. Twice daily for 7 days" required {...rxForm.getInputProps("frequency")} />
            <Textarea label="Additional Instructions" rows={2} {...rxForm.getInputProps("instructions")} />
            <Group justify="flex-end">
              <Button variant="subtle" onClick={closeRx}>Cancel</Button>
              <Button type="submit" color="violet" leftSection={<IconCheck size={16} />}>Save Prescription</Button>
            </Group>
          </Stack>
        </form>
      </Modal>

      <Modal opened={labOpen} onClose={closeLab} title="Add Lab Result" centered>
        <form onSubmit={labForm.onSubmit(submitLab)}>
          <Stack>
            <TextInput label="Test Name" required {...labForm.getInputProps("test_name")} />
            <TextInput label="LOINC Code" placeholder="e.g. 2160-0" {...labForm.getInputProps("loinc_code")} />
            <Textarea label="Result / Findings" required rows={3} {...labForm.getInputProps("result_value")} />
            <TextInput label="Reference Range" placeholder="e.g. 0.6 - 1.2 mg/dL" {...labForm.getInputProps("reference_range")} />
            <Select
              label="Status"
              data={[{ value: "false", label: "Normal" }, { value: "true", label: "Abnormal" }]}
              value={labForm.values.is_abnormal ? "true" : "false"}
              onChange={(v) => labForm.setFieldValue("is_abnormal", v === "true")}
            />
            <Group justify="flex-end">
              <Button variant="subtle" onClick={closeLab}>Cancel</Button>
              <Button type="submit" color="clinical" leftSection={<IconCheck size={16} />}>Save Lab Result</Button>
            </Group>
          </Stack>
        </form>
      </Modal>
    </Stack>
  );
}

function Section({ title, count, color, children }: { title: string; count: number; color: string; children: React.ReactNode }) {
  return (
    <Card withBorder radius="md" padding="lg">
      <Group mb="md" gap="sm">
        <Title order={4}>{title}</Title>
        <Badge color={color} variant="light">{count}</Badge>
      </Group>
      {children}
    </Card>
  );
}
