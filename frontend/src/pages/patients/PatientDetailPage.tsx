/**
 * PatientDetailPage — full patient chart with tabbed sections.
 *
 * Tabs:
 *   Overview · Encounters · Vitals · Labs · Medications · Documents · Referrals
 *
 * Role-gated: access via can_access_patient gate on the backend.
 * Break-glass flow preserved for cross-hospital access denial.
 */

import {
  Alert,
  Badge,
  Box,
  Button,
  Card,
  Center,
  Divider,
  Drawer,
  Group,
  Loader,
  Modal,
  Paper,
  PinInput,
  SimpleGrid,
  Skeleton,
  Stack,
  Table,
  Tabs,
  Text,
  Textarea,
  ThemeIcon,
  Title,
  Select,
  FileButton,
} from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import {
  IconAlertTriangle,
  IconArrowLeftRight,
  IconDownload,
  IconFlask,
  IconPill,
  IconPrinter,
  IconShield,
  IconStethoscope,
  IconUser,
  IconActivity,
  IconFolder,
} from "@tabler/icons-react";
import { ConfidentialityBadge } from "@/components/ConfidentialityBadge";
import { AreaChart } from "@mantine/charts";
import { modals } from "@mantine/modals";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import dayjs from "dayjs";
import relativeTime from "dayjs/plugin/relativeTime";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  breakGlass,
  fetchPatient,
  fetchPatientEncounters,
  fetchPatientRecords,
  fetchPatientVitals,
  queryPatientAI,
  fetchReferrals,
  createReferral,
  fetchHospitals,
  createLabOrder,
  fetchPatientDocuments,
  uploadPatientDocument,
  deletePatientDocument,
} from "@/api/endpoints";
import { useAuth } from "@/auth/AuthProvider";
import type { AIQueryResult, EncounterSummary, VitalSign, LabResult, Prescription, Referral } from "@/types";
import { isRole } from "@/constants/roles";
import { useIsPrinting } from "@/utils/useIsPrinting";

dayjs.extend(relativeTime);

// ── Tab visibility by role ─────────────────────────────────────────────────────
function useTabs(user: ReturnType<typeof useAuth>["user"]) {
  const role = user?.role;
  return {
    showEncounters:   isRole(role, "doctor", "nurse"),
    showLabs:         isRole(role, "doctor", "nurse", "lab_technician"),
    showVitals:       isRole(role, "doctor", "nurse", "hospital_admin", "super_admin"),
    showMeds:         isRole(role, "doctor", "nurse"),
    showDocs:         isRole(role, "doctor", "nurse", "hospital_admin", "super_admin"),
    showReferrals:    isRole(role, "doctor", "hospital_admin", "super_admin"),
    canCreateReferral: isRole(role, "doctor"),
    canEdit:          isRole(role, "doctor", "nurse", "receptionist", "hospital_admin", "super_admin"),
    canCreateEncounter: isRole(role, "doctor", "nurse"),
    canAlert:         isRole(role, "doctor", "nurse"),
    canFhirExport:    isRole(role, "doctor", "hospital_admin", "super_admin"),
    canQueryAI:       isRole(role, "doctor", "nurse", "hospital_admin", "super_admin"),
  };
}

export function PatientDetailPage() {
  const { nhid }   = useParams<{ nhid: string }>();
  const { user }   = useAuth();
  const navigate   = useNavigate();
  const qc         = useQueryClient();
  const perms      = useTabs(user);
  const { isPrinting, triggerPrint } = useIsPrinting();

  const getDefaultTab = () => {
    if (perms.showEncounters) return "encounters";
    if (perms.showVitals) return "vitals";
    if (perms.showLabs) return "labs";
    if (perms.showDocs) return "docs";
    if (perms.showReferrals) return "referrals";
    return null;
  };
  const [activeTab, setActiveTab] = useState<string | null>(getDefaultTab);
  const [bgOpen, { open: openBG, close: closeBG }] = useDisclosure(false);
  const [aiOpen, { open: openAI, close: closeAI }] = useDisclosure(false);
  const [bgReason, setBgReason] = useState("");
  const [bgMfaCode, setBgMfaCode] = useState("");
  const [bgLoading, setBgLoading] = useState(false);
  const [aiQuestion, setAiQuestion] = useState("");
  const [aiResult, setAiResult] = useState<AIQueryResult | null>(null);
  const [aiLoading, setAiLoading] = useState(false);

  // Lab detail modal
  const [selectedLab, setSelectedLab] = useState<LabResult | null>(null);

  // Lab order form state
  const [labOrderOpen, setLabOrderOpen] = useState(false);
  const [labOrderTest, setLabOrderTest] = useState("");
  const [labOrderPriority, setLabOrderPriority] = useState<"routine" | "urgent" | "stat">("routine");
  const [labOrderLoading, setLabOrderLoading] = useState(false);

  // Referral form state
  const [referralOpen, setReferralOpen] = useState(false);
  const [referralHospitalId, setReferralHospitalId] = useState<string | null>(null);
  const [referralReason, setReferralReason] = useState("");
  const [referralLoading, setReferralLoading] = useState(false);

  // Queries
  const { data: patient, isLoading, error } = useQuery({
    queryKey: ["patient", nhid],
    queryFn:  () => fetchPatient(nhid!).then((r) => r.data),
    enabled:  !!nhid,
  });

  const { data: encounters } = useQuery({
    queryKey: ["encounters", nhid],
    queryFn:  () => fetchPatientEncounters(nhid!).then((r) => r.data),
    enabled:  !!nhid && !!patient && perms.showEncounters,
  });

  const { data: records, isLoading: recordsLoading } = useQuery({
    queryKey: ["patient-records", nhid],
    queryFn:  () => fetchPatientRecords(nhid!).then((r) => r.data),
    enabled:  !!nhid && !!patient && (perms.showLabs || perms.showMeds),
  });

  const { data: vitals } = useQuery({
    queryKey: ["patient-vitals", nhid],
    queryFn:  () => fetchPatientVitals(nhid!).then((r) => r.data),
    enabled:  !!nhid && !!patient && perms.showVitals,
  });

  const { data: patientReferrals, isLoading: referralsLoading } = useQuery({
    queryKey: ["patient-referrals", nhid],
    queryFn:  () => fetchReferrals({ patient_nhid: nhid! }).then((r) => r.data.results ?? []),
    enabled:  !!nhid && !!patient && perms.showReferrals,
  });

  const { data: hospitalsData } = useQuery({
    queryKey: ["hospitals-list"],
    queryFn:  () => fetchHospitals().then((r) => r.data.results),
    enabled:  !!patient && perms.canCreateReferral,
  });

  const { data: patientDocuments, isLoading: docsLoading } = useQuery({
    queryKey: ["patient-documents", nhid],
    queryFn:  () => fetchPatientDocuments(nhid!).then((r) => r.data),
    enabled:  !!nhid && !!patient && perms.showDocs,
  });

  const uploadDocMutation = useMutation({
    mutationFn: ({ file, description }: { file: File; description: string }) =>
      uploadPatientDocument(nhid!, file, description),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["patient-documents", nhid] });
      notifications.show({ color: "green", title: "Document uploaded", message: "File saved to patient record." });
    },
    onError: (e: unknown) => {
      const axiosErr = e as { response?: { data?: { error?: string } } };
      const msg = axiosErr?.response?.data?.error || "Upload failed. Check file size (max 20 MB).";
      notifications.show({ color: "red", message: msg });
    },
  });

  const deleteDocMutation = useMutation({
    mutationFn: (docId: number) => deletePatientDocument(nhid!, docId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["patient-documents", nhid] });
      notifications.show({ color: "green", message: "Document deleted." });
    },
    onError: () => notifications.show({ color: "red", message: "Failed to delete document." }),
  });

  const [docDescription, setDocDescription] = useState("");

  // Break-glass request
  async function handleBreakGlass() {
    if (bgReason.trim().length < 20) return; // guarded by button disabled state
    if (user?.mfa_enabled && bgMfaCode.length < 6) return;
    setBgLoading(true);
    try {
      await breakGlass(nhid!, bgReason.trim(), user?.mfa_enabled ? bgMfaCode : undefined);
      closeBG();
      setBgReason("");
      setBgMfaCode("");
      qc.invalidateQueries({ queryKey: ["patient", nhid] });
      notifications.show({
        color: "orange",
        title: "Break-glass access granted",
        message: "Access granted for 1 hour. This action has been logged.",
      });
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { error?: string } } };
      const msg = axiosErr?.response?.data?.error ?? "Failed to request break-glass access.";
      notifications.show({ color: "red", message: msg });
    } finally {
      setBgLoading(false);
    }
  }

  // FHIR export
  async function handleFhirDownload() {
    try {
      const { default: api } = await import("@/api/client");
      const res = await api.get(`/fhir/Patient/${nhid}/$everything`, {
        responseType: "blob",
        headers: { Accept: "application/fhir+json" },
      });
      const url = URL.createObjectURL(res.data as Blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `fhir-${nhid}-${dayjs().format("YYYYMMDD")}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      notifications.show({ color: "red", message: "FHIR export failed. Check your permissions." });
    }
  }

  // AI query
  async function handleAIQuery() {
    if (!aiQuestion.trim()) return;
    setAiLoading(true);
    setAiResult(null);
    try {
      const r = await queryPatientAI(nhid!, aiQuestion.trim());
      setAiResult(r.data);
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { error?: string } } };
      const msg = axiosErr?.response?.data?.error ?? "AI query failed.";
      setAiResult({ answer: "", error: msg, configured: false, provider: "gemini", model: "", context_size: 0 });
    } finally {
      setAiLoading(false);
    }
  }

  async function handleOrderLab() {
    if (!labOrderTest || !nhid) return;
    setLabOrderLoading(true);
    try {
      await createLabOrder(nhid, { test_name: labOrderTest, priority: labOrderPriority });
      qc.invalidateQueries({ queryKey: ["patient-records", nhid] });
      notifications.show({
        title: "Lab Order Placed",
        message: `Successfully ordered "${labOrderTest}" for ${patient?.full_name}.`,
        color: "green",
      });
      setLabOrderTest("");
      setLabOrderPriority("routine");
      setLabOrderOpen(false);
    } catch {
      notifications.show({ color: "red", message: "Failed to place lab order. Please try again." });
    } finally {
      setLabOrderLoading(false);
    }
  }

  async function handleReferPatient() {
    if (!referralHospitalId || !referralReason || !nhid) return;
    setReferralLoading(true);
    try {
      await createReferral({
        patient_nhid: nhid,
        to_hospital: Number(referralHospitalId),
        reason: referralReason,
        priority: "routine",
      });
      qc.invalidateQueries({ queryKey: ["patient-referrals", nhid] });
      notifications.show({
        title: "Referral Created",
        message: "Referral submitted successfully.",
        color: "green",
      });
      setReferralHospitalId(null);
      setReferralReason("");
      setReferralOpen(false);
    } catch {
      notifications.show({ color: "red", message: "Failed to create referral. Please try again." });
    } finally {
      setReferralLoading(false);
    }
  }

  if (isLoading) {
    return (
      <Stack gap="md">
        <Skeleton height={120} radius="lg" />
        <Skeleton height={40} />
        <Skeleton height={300} />
      </Stack>
    );
  }

  if (error) {
    return (
      <Center h={400}>
        <Stack align="center" maw={400}>
          <ThemeIcon size={64} color="red" variant="light" radius="xl">
            <IconAlertTriangle size={36} />
          </ThemeIcon>
          <Title order={3} ta="center">Access Denied</Title>
          <Text c="dimmed" ta="center">
            You do not have access to patient{" "}
            <Text component="span" fw={700} ff="monospace">{nhid}</Text>.
          </Text>
          <Button leftSection={<IconShield size={16} />} color="orange" onClick={openBG}>
            Request Emergency Access (Break Glass)
          </Button>
          <Button variant="subtle" onClick={() => navigate(-1)}>Go Back</Button>
          <BreakGlassModal
            opened={bgOpen}
            onClose={closeBG}
            reason={bgReason}
            setReason={setBgReason}
            mfaCode={bgMfaCode}
            setMfaCode={setBgMfaCode}
            mfaEnabled={user?.mfa_enabled ?? false}
            onConfirm={handleBreakGlass}
            loading={bgLoading}
          />
        </Stack>
      </Center>
    );
  }

  if (!patient) return null;

  const isCross = patient.is_cross_hospital;
  const isBreakGlass = patient.access_basis === "break_glass";
  const activeAlerts = patient.alerts?.filter((a) => a.is_active) ?? [];

  return (
    <Stack gap="md">
      {/* Printable Chart View (only mounted in DOM during active print to prevent hidden-DOM PHI leak) */}
      {isPrinting && (
        <div className="print-only" style={{ padding: "20px" }}>
          <Title order={2} mb="xs">{patient.full_name}</Title>
          <Text size="sm" c="dimmed" mb="md">
            NHID: {patient.universal_id} | DOB: {patient.date_of_birth} | Sex: {patient.sex_display} | Blood Group: {patient.blood_group_display || patient.blood_group || "—"}
          </Text>
          <Divider my="md" />
          <Title order={3} mb="xs">Active Alerts & Risk Factors</Title>
          {activeAlerts.length > 0 ? (
            <Group gap="xs" mb="md">
              {activeAlerts.map(a => (
                <Badge key={a.id} color={a.is_high_risk ? "red" : "orange"} variant="filled">{a.label}</Badge>
              ))}
            </Group>
          ) : (
            <Text size="sm" c="dimmed" mb="md">None recorded.</Text>
          )}
          <Divider my="md" />
          <Title order={3} mb="xs">Recent Encounters</Title>
          {encounters && encounters.length > 0 ? (
            <Stack gap="xs" mb="md">
              {encounters.slice(0, 5).map(e => (
                <Box key={e.id} style={{ borderBottom: "1px solid #ddd", paddingBottom: "8px" }}>
                  <Text size="xs" c="dimmed">{e.created_by?.full_name ?? "—"}</Text>
                </Box>
              ))}
            </Stack>
          ) : (
            <Text size="sm" c="dimmed" mb="md">No encounters recorded.</Text>
          )}
        </div>
      )}
      {/* ── Banners ─────────────────────────────────────────────────────────── */}
      {isCross && (
        <Alert color="yellow" icon={<IconArrowLeftRight />} title={`Cross-hospital access — ${patient.access_basis}`}>
          Registered at <strong>{patient.registered_at_hospital?.name ?? "another hospital"}</strong>.
          You are accessing from <strong>{user?.hospital?.name ?? "your hospital"}</strong>. Access is logged.
        </Alert>
      )}
      {isBreakGlass && (
        <Alert color="orange" icon={<IconShield />} title="Break-Glass Access Active">
          You have temporary emergency access (&lt; 1 hour). This access is logged and will be reviewed.
        </Alert>
      )}

      {/* TWO COLUMN CLINICAL CHART */}
      <SimpleGrid cols={{ base: 1, lg: 3 }} spacing="md">
        
        {/* LEFT COLUMN: Summary card & Actions */}
        <Stack gap="md" style={{ gridColumn: "span 1" }}>
          <Card withBorder radius="md" p="md" bg="var(--surface-2)">
            <Box ta="center" mb="md">
              <ThemeIcon size={64} radius="xl" color="medsync" variant="light" mb="xs">
                <IconUser size={36} />
              </ThemeIcon>
              <Title order={3}>{patient.full_name}</Title>
              <Text ff="monospace" size="xs" c="dimmed">{patient.universal_id}</Text>
            </Box>

            <Divider mb="sm" />

            <Stack gap={8}>
              {[
                ["DOB", `${patient.date_of_birth} (${dayjs().diff(dayjs(patient.date_of_birth), 'year')} yrs)`],
                ["Gender", patient.sex_display],
                ["Blood Group", patient.blood_group_display || patient.blood_group || "—"],
                ["National ID", patient.national_id || "—"],
                ["Phone", patient.phone || "—"],
                ["Hospital", patient.registered_at_hospital?.name || "—"],
                ["Registered", dayjs(patient.created_at).format("DD MMM YYYY")],
              ].map(([label, value]) => (
                <Group key={label} justify="space-between" wrap="nowrap">
                  <Text size="xs" c="dimmed">{label}</Text>
                  <Text size="xs" fw={500} ta="right">{value}</Text>
                </Group>
              ))}
            </Stack>

            {/* Allergies / Alerts sub-section inside left card */}
            <Box mt="md" pt="md" style={{ borderTop: "1px solid var(--border)" }}>
              <Group gap="xs" mb={8}>
                <IconAlertTriangle size={14} color="var(--accent-red)" />
                <Text size="xs" fw={700} c="red">Allergies & High Risks</Text>
              </Group>
              {activeAlerts.length > 0 ? (
                <Group gap="xs" wrap="wrap">
                  {activeAlerts.map((a) => (
                    <Badge
                      key={a.id}
                      color={a.is_high_risk ? "red" : "orange"}
                      variant="filled"
                      size="xs"
                    >
                      {a.label}
                    </Badge>
                  ))}
                </Group>
              ) : (
                <Text size="xs" c="dimmed">No recorded allergies or alerts.</Text>
              )}
            </Box>
          </Card>

          {/* Quick Actions Panel */}
          {(perms.canCreateEncounter || user?.role === "doctor" || user?.is_admin_level || perms.canQueryAI) && (
            <Card withBorder radius="md" p="md" bg="var(--surface-2)">
              <Text size="xs" fw={700} c="dimmed" tt="uppercase" mb="xs" style={{ letterSpacing: 0.5 }}>
                Quick Actions
              </Text>
              <Stack gap="xs">
                {perms.canCreateEncounter && (
                  <Button
                    component={Link}
                    to={`/patients/${nhid}/encounters/new`}
                    variant="light"
                    leftSection={<IconStethoscope size={16} />}
                    fullWidth
                    size="sm"
                  >
                    New Encounter
                  </Button>
                )}

                {perms.canCreateEncounter && (
                  <Button
                    variant="light"
                    color="teal"
                    leftSection={<IconFlask size={16} />}
                    fullWidth
                    size="sm"
                    onClick={() => setLabOrderOpen(true)}
                  >
                    Order Lab Test
                  </Button>
                )}

                {user?.role === "doctor" && (
                  <Button
                    component={Link}
                    to={`/patients/${nhid}?tab=encounters`}
                    variant="light"
                    color="violet"
                    leftSection={<IconPill size={16} />}
                    fullWidth
                    size="sm"
                  >
                    Write Prescription
                  </Button>
                )}

                {perms.canCreateReferral && (
                  <Button
                    variant="light"
                    color="orange"
                    leftSection={<IconArrowLeftRight size={16} />}
                    fullWidth
                    size="sm"
                    onClick={() => setReferralOpen(true)}
                  >
                    Refer Patient
                  </Button>
                )}

                {perms.canQueryAI && (
                  <Button
                    variant="outline"
                    color="indigo"
                    leftSection={<IconActivity size={16} />}
                    fullWidth
                    size="sm"
                    onClick={openAI}
                  >
                    AI Consultation Assistant
                  </Button>
                )}

                <Button
                  variant="light"
                  color="gray"
                  leftSection={<IconPrinter size={16} />}
                  fullWidth
                  size="sm"
                  onClick={triggerPrint}
                  aria-label="Print patient chart"
                >
                  Print Chart
                </Button>

                {perms.canFhirExport && (
                  <Button
                    variant="light"
                    color="grape"
                    leftSection={<IconDownload size={16} />}
                    fullWidth
                    size="sm"
                    onClick={handleFhirDownload}
                    aria-label="Download FHIR R4 bundle"
                  >
                    Download FHIR Bundle
                  </Button>
                )}
              </Stack>
            </Card>
          )}
        </Stack>

        {/* RIGHT COLUMN: Tab panels */}
        <div style={{ gridColumn: "span 2" }}>
          <Tabs value={activeTab} onChange={setActiveTab} variant="outline">
            <Tabs.List>
              {perms.showEncounters && (
                <Tabs.Tab value="encounters" leftSection={<IconStethoscope size={14} />}>Encounters</Tabs.Tab>
              )}
              {perms.showVitals && (
                <Tabs.Tab value="vitals" leftSection={<IconActivity size={14} />}>Vitals</Tabs.Tab>
              )}
              {perms.showLabs && (
                <Tabs.Tab value="labs" leftSection={<IconFlask size={14} />}>Lab results</Tabs.Tab>
              )}
              {perms.showMeds && (
                <Tabs.Tab value="meds" leftSection={<IconPill size={14} />}>Medications</Tabs.Tab>
              )}
              {perms.showDocs && (
                <Tabs.Tab value="docs" leftSection={<IconFolder size={14} />}>Documents</Tabs.Tab>
              )}
              {perms.showReferrals && (
                <Tabs.Tab value="referrals" leftSection={<IconArrowLeftRight size={14} />}>Referrals</Tabs.Tab>
              )}
            </Tabs.List>

            {/* TAB 1: Encounters */}
            {perms.showEncounters && (
              <Tabs.Panel value="encounters" pt="md">
                <Stack gap="sm">
                  {encounters && encounters.length > 0 ? (
                    encounters.map((enc) => (
                      <EncounterRow key={enc.id} enc={enc} nhid={nhid!} />
                    ))
                  ) : (
                    <Text c="dimmed" ta="center" py="xl">No encounters on record.</Text>
                  )}
                </Stack>
              </Tabs.Panel>
            )}

            {/* TAB 2: Vitals */}
            {perms.showVitals && (
              <Tabs.Panel value="vitals" pt="md">
                <VitalsTab vitals={vitals} nhid={nhid!} />
              </Tabs.Panel>
            )}

            {/* TAB 3: Lab Results with abnormalities flags */}
            {perms.showLabs && (
              <Tabs.Panel value="labs" pt="md">
                {recordsLoading ? <Skeleton height={200} /> : (
                  !records?.lab_results.length ? (
                    <Text c="dimmed" ta="center" py="xl">No lab results recorded.</Text>
                  ) : (
                    <Table.ScrollContainer minWidth={600}>
                      <Table striped highlightOnHover>
                        <Table.Thead>
                          <Table.Tr>
                            <Table.Th>Test</Table.Th>
                            <Table.Th>LOINC</Table.Th>
                            <Table.Th>Result</Table.Th>
                            <Table.Th>Ref Range</Table.Th>
                            <Table.Th>Flag</Table.Th>
                          </Table.Tr>
                        </Table.Thead>
                        <Table.Tbody>
                          {records.lab_results.map((lab: LabResult) => {
                            const isCritical = lab.is_abnormal && lab.result_value?.includes("CRITICAL");
                            return (
                              <Table.Tr
                                key={lab.id}
                                style={{
                                  cursor: "pointer",
                                  backgroundColor: isCritical ? "var(--bg-red)" : undefined,
                                }}
                                onClick={() => setSelectedLab(lab)}
                              >
                                <Table.Td fw={600} style={{ color: isCritical ? "var(--accent-red)" : undefined }}>
                                  {lab.test_name}
                                </Table.Td>
                                <Table.Td>{lab.loinc_code || "—"}</Table.Td>
                                <Table.Td fw={700} style={{ color: isCritical ? "var(--accent-red)" : undefined }}>
                                  {lab.result_value}
                                </Table.Td>
                                <Table.Td>{lab.reference_range || "—"}</Table.Td>
                                <Table.Td>
                                  <Badge color={lab.is_abnormal ? "red" : "green"} variant="filled">
                                    {lab.is_abnormal ? "Abnormal" : "Normal"}
                                  </Badge>
                                </Table.Td>
                              </Table.Tr>
                            );
                          })}
                        </Table.Tbody>
                      </Table>
                    </Table.ScrollContainer>
                  )
                )}
              </Tabs.Panel>
            )}

            {/* TAB 4: Medications */}
            {perms.showMeds && (
              <Tabs.Panel value="meds" pt="md">
                <Card withBorder radius="md" p="md" bg="var(--surface-2)">
                  <Group justify="space-between" mb="md">
                    <Text fw={600} size="sm" tt="uppercase" c="dimmed">Prescriptions list</Text>
                    {user?.role === "doctor" && (
                      <Button size="xs" component={Link} to="/prescriptions" leftSection={<IconPill size={12} />}>
                        Write new prescription
                      </Button>
                    )}
                  </Group>
                  
                  {recordsLoading ? <Skeleton height={150} /> : (
                    !records?.prescriptions.length ? (
                      <Text c="dimmed" ta="center" py="xl">No prescriptions active.</Text>
                    ) : (
                      <Table striped highlightOnHover>
                        <Table.Thead>
                          <Table.Tr>
                            <Table.Th>Drug Name</Table.Th>
                            <Table.Th>Dose</Table.Th>
                            <Table.Th>Frequency</Table.Th>
                            <Table.Th>Instructions</Table.Th>
                          </Table.Tr>
                        </Table.Thead>
                        <Table.Tbody>
                          {records.prescriptions.map((rx: Prescription) => (
                              <Table.Tr key={rx.id}>
                                <Table.Td fw={600}>{rx.drug_name}</Table.Td>
                                <Table.Td>{rx.dosage}</Table.Td>
                                <Table.Td>{rx.frequency}</Table.Td>
                                <Table.Td>
                                  <Text size="xs" c="dimmed">{rx.instructions || "—"}</Text>
                                </Table.Td>
                              </Table.Tr>
                            ))}
                        </Table.Tbody>
                      </Table>
                    )
                  )}
                </Card>
              </Tabs.Panel>
            )}

            {/* TAB 5: Documents */}
            {perms.showDocs && (
              <Tabs.Panel value="docs" pt="md">
                <Card withBorder radius="md" p="md" bg="var(--surface-2)">
                  <Group justify="space-between" mb="md">
                    <Text fw={600} size="sm" tt="uppercase" c="dimmed">Patient Documents</Text>
                    <Group gap="xs">
                      <Textarea
                        placeholder="Description (optional)"
                        size="xs"
                        value={docDescription}
                        onChange={(e) => setDocDescription(e.currentTarget.value)}
                        minRows={1}
                        autosize
                        style={{ width: 180 }}
                      />
                      <FileButton
                        onChange={(file) => {
                          if (file) {
                            uploadDocMutation.mutate({ file, description: docDescription });
                            setDocDescription("");
                          }
                        }}
                      >
                        {(props) => (
                          <Button
                            {...props}
                            size="xs"
                            loading={uploadDocMutation.isPending}
                            leftSection={<IconDownload size={12} style={{ transform: "rotate(180deg)" }} />}
                          >
                            Upload file
                          </Button>
                        )}
                      </FileButton>
                    </Group>
                  </Group>

                  {docsLoading ? (
                    <Stack gap="xs">
                      {[1, 2, 3].map((i) => <Skeleton key={i} height={36} radius="sm" />)}
                    </Stack>
                  ) : !patientDocuments?.length ? (
                    <Text c="dimmed" ta="center" py="xl" size="sm">No documents uploaded yet.</Text>
                  ) : (
                    <Table striped highlightOnHover>
                      <Table.Thead>
                        <Table.Tr>
                          <Table.Th>File name</Table.Th>
                          <Table.Th>Sensitivity</Table.Th>
                          <Table.Th>Description</Table.Th>
                          <Table.Th>Size</Table.Th>
                          <Table.Th>Uploaded by</Table.Th>
                          <Table.Th>Date</Table.Th>
                          <Table.Th>Actions</Table.Th>
                        </Table.Tr>
                      </Table.Thead>
                      <Table.Tbody>
                        {patientDocuments.map((doc) => (
                          <Table.Tr key={doc.id}>
                            <Table.Td fw={600}>{doc.original_name}</Table.Td>
                            <Table.Td>
                              <ConfidentialityBadge level={doc.confidentiality} showNormal size="xs" />
                            </Table.Td>
                            <Table.Td>{doc.description || "—"}</Table.Td>
                            <Table.Td>{doc.file_size_kb} KB</Table.Td>
                            <Table.Td>{doc.uploaded_by_name || "—"}</Table.Td>
                            <Table.Td>{dayjs(doc.created_at).format("DD MMM YYYY")}</Table.Td>
                            <Table.Td>
                              <Group gap="xs">
                                <Button
                                  size="xs"
                                  variant="light"
                                  component="a"
                                  href={doc.download_url ?? "#"}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  disabled={!doc.download_url}
                                >
                                  Download
                                </Button>
                                <Button
                                  size="xs"
                                  variant="light"
                                  color="red"
                                  loading={deleteDocMutation.isPending && deleteDocMutation.variables === doc.id}
                                  onClick={() =>
                                    modals.openConfirmModal({
                                      title: "Delete document",
                                      children: (
                                        <Text size="sm">
                                          Are you sure you want to delete{" "}
                                          <strong>{doc.original_name}</strong>?
                                          This action cannot be undone.
                                        </Text>
                                      ),
                                      labels: { confirm: "Delete", cancel: "Cancel" },
                                      confirmProps: { color: "red" },
                                      onConfirm: () => deleteDocMutation.mutate(doc.id),
                                    })
                                  }
                                >
                                  Delete
                                </Button>
                              </Group>
                            </Table.Td>
                          </Table.Tr>
                        ))}
                      </Table.Tbody>
                    </Table>
                  )}
                </Card>
              </Tabs.Panel>
            )}

            {/* TAB 6: Referrals */}
            {perms.showReferrals && (
              <Tabs.Panel value="referrals" pt="md">
                <Card withBorder radius="md" p="md" bg="var(--surface-2)">
                  <Group justify="space-between" mb="md">
                    <Text fw={600} size="sm" tt="uppercase" c="dimmed">Referrals Tracking</Text>
                    {perms.canCreateReferral && (
                      <Button size="xs" leftSection={<IconArrowLeftRight size={12} />} onClick={() => setReferralOpen(true)}>
                        New Referral
                      </Button>
                    )}
                  </Group>

                  {referralsLoading ? <Skeleton height={150} /> : (
                    !patientReferrals?.length ? (
                      <Text c="dimmed" ta="center" py="xl">No referrals on record.</Text>
                    ) : (
                      <Table striped>
                        <Table.Thead>
                          <Table.Tr>
                            <Table.Th>To Hospital</Table.Th>
                            <Table.Th>From</Table.Th>
                            <Table.Th>Status</Table.Th>
                            <Table.Th>Priority</Table.Th>
                            <Table.Th>Reason</Table.Th>
                            <Table.Th>Date</Table.Th>
                          </Table.Tr>
                        </Table.Thead>
                        <Table.Tbody>
                          {patientReferrals.map((r: Referral) => (
                            <Table.Tr key={r.id}>
                              <Table.Td fw={600}>{r.to_hospital_name}</Table.Td>
                              <Table.Td>{r.from_hospital_name}</Table.Td>
                              <Table.Td>
                                <Badge
                                  color={
                                    r.status === "accepted" ? "green" :
                                    r.status === "rejected" ? "red" :
                                    r.status === "completed" ? "blue" : "orange"
                                  }
                                  variant="light"
                                >
                                  {r.status_display}
                                </Badge>
                              </Table.Td>
                              <Table.Td>
                                <Badge color={r.priority === "stat" ? "red" : r.priority === "urgent" ? "orange" : "gray"} variant="light" size="xs">
                                  {r.priority_display}
                                </Badge>
                              </Table.Td>
                              <Table.Td><Text size="xs" c="dimmed">{r.reason}</Text></Table.Td>
                              <Table.Td><Text size="xs" c="dimmed">{dayjs(r.created_at).format("DD MMM YYYY")}</Text></Table.Td>
                            </Table.Tr>
                          ))}
                        </Table.Tbody>
                      </Table>
                    )
                  )}
                </Card>
              </Tabs.Panel>
            )}
          </Tabs>
        </div>
      </SimpleGrid>

      {/* AI Assistant Drawer */}
      <Drawer
        opened={aiOpen}
        onClose={closeAI}
        position="right"
        size={520}
        title={
          <Group gap="xs">
            <IconActivity size={18} />
            <Text fw={700}>AI Consultation Assistant</Text>
          </Group>
        }
        styles={{ header: { borderBottom: "1px solid var(--mantine-color-default-border)" } }}
      >
        <Stack gap="md" p="xs">
          <Text size="sm" c="dimmed">
            Ask clinical questions about this patient chart. All queries are fully logged in the immutable audit trail.
          </Text>

          <Textarea
            placeholder="e.g. Summarise the patient's vitals trend and check for penicillin allergies."
            value={aiQuestion}
            onChange={(e) => setAiQuestion(e.currentTarget.value)}
            minRows={4}
            maxLength={500}
            autosize
          />
          <Group justify="space-between">
            <Text size="xs" c="dimmed">{aiQuestion.length}/500</Text>
            <Button
              onClick={handleAIQuery}
              loading={aiLoading}
              disabled={!aiQuestion.trim()}
              color="indigo"
            >
              Query Records
            </Button>
          </Group>

          {aiLoading && (
            <Center py="xl">
              <Stack align="center" gap="xs">
                <Loader color="indigo" />
                <Text size="sm" c="dimmed">Querying patient records…</Text>
              </Stack>
            </Center>
          )}

          {aiResult && !aiLoading && (
            <Card withBorder radius="md" p="md">
              {aiResult.error ? (
                <Stack gap="xs">
                  <Text fw={600} c="red">AI Service Unavailable</Text>
                  <Text size="sm">{aiResult.error}</Text>
                </Stack>
              ) : (
                <Stack gap="sm">
                  <Text fw={600} size="sm">AI Response</Text>
                  <Text size="sm" style={{ whiteSpace: "pre-wrap", lineHeight: 1.6 }}>
                    {aiResult.answer}
                  </Text>
                  <Divider />
                  <Text size="xs" c="dimmed">
                    Generated securely from authorized clinical entries.
                  </Text>
                </Stack>
              )}
            </Card>
          )}
        </Stack>
      </Drawer>

      {/* Lab detail modal */}
      <Modal opened={!!selectedLab} onClose={() => setSelectedLab(null)} title="Lab Result Detail" centered>
        {selectedLab && (
          <Stack gap="md">
            <Group justify="space-between">
              <Title order={4}>{selectedLab.test_name}</Title>
              <Badge color={selectedLab.is_abnormal ? "red" : "green"}>
                {selectedLab.is_abnormal ? "Abnormal" : "Normal"}
              </Badge>
            </Group>
            <Divider />
            <SimpleGrid cols={2}>
              <Box><Text size="xs" c="dimmed">RESULT VALUE</Text><Text fw={700} size="lg">{selectedLab.result_value}</Text></Box>
              <Box><Text size="xs" c="dimmed">REFERENCE RANGE</Text><Text size="sm">{selectedLab.reference_range || "—"}</Text></Box>
            </SimpleGrid>
            <Box>
              <Text size="xs" c="dimmed">LOINC CODE</Text>
              <Text size="sm" ff="monospace">{selectedLab.loinc_code || "—"}</Text>
            </Box>
            <Box>
              <Text size="xs" c="dimmed">ORDERED BY</Text>
              <Text size="sm">{selectedLab.created_by?.full_name || "—"}</Text>
            </Box>
            <Box>
              <Text size="xs" c="dimmed">COLLECTED TIME</Text>
              <Text size="sm">{dayjs(selectedLab.created_at).format("DD MMM YYYY HH:mm")}</Text>
            </Box>
          </Stack>
        )}
      </Modal>

      {/* Lab Order Modal */}
      <Modal opened={labOrderOpen} onClose={() => setLabOrderOpen(false)} title="Order Laboratory Test" centered>
        <Stack gap="md">
          <Select
            label="Laboratory Test Name"
            placeholder="Select a test..."
            data={[
              "Full blood count (FBC)",
              "Malaria RDT / Blood Film",
              "Liver Function Test (LFT)",
              "Renal Function Test (KFT)",
              "Lipid Profile",
              "Urine microscopy & culture",
              "Thyroid Function Test (TFT)",
              "Blood glucose (fasting)",
              "HbA1c",
            ]}
            value={labOrderTest}
            onChange={(v: string | null) => setLabOrderTest(v || "")}
          />
          <Select
            label="Priority"
            data={[
              { value: "routine", label: "Routine" },
              { value: "urgent", label: "Urgent" },
              { value: "stat", label: "STAT (Emergency)" },
            ]}
            value={labOrderPriority}
            onChange={(v) => setLabOrderPriority((v as "routine" | "urgent" | "stat") || "routine")}
          />
          <Group justify="flex-end">
            <Button variant="outline" color="gray" onClick={() => setLabOrderOpen(false)}>Cancel</Button>
            <Button color="teal" onClick={handleOrderLab} loading={labOrderLoading} disabled={!labOrderTest}>Place Order</Button>
          </Group>
        </Stack>
      </Modal>

      {/* Referral Modal */}
      <Modal opened={referralOpen} onClose={() => setReferralOpen(false)} title="Refer Patient to Another Hospital" centered>
        <Stack gap="md">
          <Select
            label="Target Hospital"
            placeholder="Select hospital..."
            data={(hospitalsData || [])
              .filter((h) => h.id !== patient?.registered_at_hospital?.id)
              .map((h) => ({ value: String(h.id), label: `${h.name} · ${h.city || h.code}` }))}
            value={referralHospitalId}
            onChange={setReferralHospitalId}
            searchable
          />
          <Textarea
            label="Reason for Referral"
            placeholder="Enter clinical reasons and summary of findings..."
            value={referralReason}
            onChange={(e) => setReferralReason(e.currentTarget.value)}
            rows={3}
          />
          <Group justify="flex-end">
            <Button variant="outline" color="gray" onClick={() => setReferralOpen(false)}>Cancel</Button>
            <Button color="orange" onClick={handleReferPatient} loading={referralLoading} disabled={!referralHospitalId || !referralReason}>Submit Referral</Button>
          </Group>
        </Stack>
      </Modal>

      {/* Break-glass modal */}
      <BreakGlassModal
        opened={bgOpen}
        onClose={closeBG}
        reason={bgReason}
        setReason={setBgReason}
        mfaCode={bgMfaCode}
        setMfaCode={setBgMfaCode}
        mfaEnabled={user?.mfa_enabled ?? false}
        onConfirm={handleBreakGlass}
        loading={bgLoading}
      />
    </Stack>
  );
}

function EncounterRow({ enc, nhid: _nhid }: { enc: EncounterSummary; nhid: string }) {
  return (
    <Card withBorder radius="md" p="md">
      <Group justify="space-between">
        <Group gap="sm">
          <ThemeIcon size={36} radius="md" color="medsync" variant="light">
            <IconStethoscope size={20} />
          </ThemeIcon>
          <Box>
            <Group gap="xs">
              <Badge variant="light" size="sm">{enc.encounter_type_display}</Badge>
              <ConfidentialityBadge level={enc.confidentiality} size="xs" />
              {enc.is_cross_hospital && (
                <Badge color="yellow" size="xs" leftSection={<IconArrowLeftRight size={10} />}>
                  External — {enc.created_at_hospital?.name}
                </Badge>
              )}
              {enc.has_abnormal_labs && (
                <Badge color="red" size="xs" leftSection={<IconAlertTriangle size={10} />}>
                  Abnormal Lab
                </Badge>
              )}
            </Group>
            <Text size="xs" c="dimmed" mt={2}>
              {enc.created_by?.full_name ?? "Unknown"} · {enc.created_at_hospital?.name ?? "—"} · {dayjs(enc.created_at).format("DD MMM YYYY")}
            </Text>
          </Box>
        </Group>
        <Button
          component={Link}
          to={`/encounters/${enc.id}`}
          size="xs"
          variant="light"
        >
          Open
        </Button>
      </Group>
    </Card>
  );
}

function VitalsTab({ vitals, nhid: _nhid }: { vitals?: VitalSign[]; nhid: string }) {
  if (!vitals) return <Skeleton height={300} />;
  if (vitals.length === 0) {
    return (
      <Text c="dimmed" ta="center" py="xl">
        No vitals recorded for this patient.
      </Text>
    );
  }

  const chartData = [...vitals].reverse().map((v) => ({
    date:  dayjs(v.recorded_at).format("DD MMM HH:mm"),
    "HR (bpm)":    v.heart_rate ?? null,
    "BP Sys":      v.bp_systolic ?? null,
    "BP Dia":      v.bp_diastolic ?? null,
    "SpO₂ (%)":   v.spo2 ? Number(v.spo2) : null,
    "Temp (°C)":   v.temperature ? Number(v.temperature) : null,
  }));

  const latest = vitals[0];

  return (
    <Stack gap="lg">
      <Card withBorder radius="md" p="md">
        <Text fw={600} size="sm" mb="sm">Latest Reading — {dayjs(latest.recorded_at).format("DD MMM YYYY HH:mm")}</Text>
        <SimpleGrid cols={{ base: 2, sm: 5 }} spacing="sm">
          {[
            ["Temp",      latest.temperature ? `${latest.temperature}°C` : "—", "blue"],
            ["HR",        latest.heart_rate ? `${latest.heart_rate} bpm` : "—", "red"],
            ["BP",        (latest.bp_systolic && latest.bp_diastolic) ? `${latest.bp_systolic}/${latest.bp_diastolic}` : "—", "orange"],
            ["SpO₂",     latest.spo2 ? `${latest.spo2}%` : "—", "teal"],
            ["Pain",      latest.pain_score != null ? `${latest.pain_score}/10` : "—", "violet"],
          ].map(([label, value, color]) => (
            <Paper key={label} withBorder p="sm" radius="md" ta="center">
              <Text size="xs" c="dimmed" tt="uppercase">{label}</Text>
              <Text fw={700} size="lg" c={color}>{String(value)}</Text>
            </Paper>
          ))}
        </SimpleGrid>
      </Card>

      {chartData.length > 1 && (
        <Card withBorder radius="md" p="md">
          <Text fw={600} size="sm" mb="md">Trend</Text>
          <Box role="img" aria-label="Vitals trend chart showing Heart Rate, Systolic Blood Pressure, and SpO2 readings over time">
            <AreaChart
              h={220}
              data={chartData}
              dataKey="date"
              series={[
                { name: "HR (bpm)",  color: "red" },
                { name: "BP Sys",    color: "orange" },
                { name: "SpO₂ (%)", color: "teal" },
              ]}
              curveType="monotone"
              connectNulls
              tickLine="x"
              gridAxis="y"
            />
          </Box>
        </Card>
      )}

      <Table.ScrollContainer minWidth={800}>
        <Table striped withTableBorder withColumnBorders>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Recorded</Table.Th>
              <Table.Th>Temp (°C)</Table.Th>
              <Table.Th>HR (bpm)</Table.Th>
              <Table.Th>RR</Table.Th>
              <Table.Th>BP</Table.Th>
              <Table.Th>SpO₂ (%)</Table.Th>
              <Table.Th>Pain</Table.Th>
              <Table.Th>By</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {vitals.map((v) => (
              <Table.Tr key={v.id}>
                <Table.Td>
                  <Text size="xs">{dayjs(v.recorded_at).format("DD MMM HH:mm")}</Text>
                </Table.Td>
                <Table.Td>{v.temperature ?? "—"}</Table.Td>
                <Table.Td>{v.heart_rate ?? "—"}</Table.Td>
                <Table.Td>{v.respiratory_rate ?? "—"}</Table.Td>
                <Table.Td>
                  {v.bp_systolic && v.bp_diastolic
                    ? `${v.bp_systolic}/${v.bp_diastolic}`
                    : "—"}
                </Table.Td>
                <Table.Td>{v.spo2 ?? "—"}</Table.Td>
                <Table.Td>
                  {v.pain_score != null ? (
                    <Badge
                      size="xs"
                      color={v.pain_score >= 7 ? "red" : v.pain_score >= 4 ? "orange" : "green"}
                      variant="light"
                    >
                      {v.pain_score}/10
                    </Badge>
                  ) : "—"}
                </Table.Td>
                <Table.Td>
                  <Text size="xs" c="dimmed">{v.recorded_by_name ?? "—"}</Text>
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
    </Stack>
  );
}

function BreakGlassModal({
  opened, onClose, reason, setReason, mfaCode, setMfaCode, mfaEnabled, onConfirm, loading,
}: {
  opened: boolean;
  onClose: () => void;
  reason: string;
  setReason: (v: string) => void;
  mfaCode: string;
  setMfaCode: (v: string) => void;
  mfaEnabled: boolean;
  onConfirm: () => void;
  loading: boolean;
}) {
  const reasonTooShort = reason.trim().length < 20;
  const needsMfa = mfaEnabled && mfaCode.length < 6;
  const confirmDisabled = reasonTooShort || needsMfa;
  const confirmDescId = "bg-confirm-desc";

  return (
    <Modal opened={opened} onClose={onClose} title="Emergency Access Request" centered>
      <Stack>
        <Alert color="orange" icon={<IconAlertTriangle />}>
          <Text size="sm" fw={700}>This action is logged in the immutable audit trail.</Text>
          <Text size="sm">Unjustified break-glass access may result in disciplinary action.</Text>
        </Alert>

        <Box>
          <Textarea
            label="Clinical justification"
            description="Minimum 20 characters. Explain why emergency access is required."
            placeholder="E.g. Patient presented unconscious in A&E; no prior clinical records available…"
            value={reason}
            onChange={(e) => setReason(e.currentTarget.value)}
            minRows={4}
            autoFocus
            error={reasonTooShort && reason.length > 0 ? "At least 20 characters required" : undefined}
          />
          <Text size="xs" c={reasonTooShort ? "red" : "dimmed"} ta="right" mt={4}>
            {reason.length} / 20 minimum
          </Text>
        </Box>

        {mfaEnabled && (
          <Box>
            <Text size="sm" fw={500} mb={6}>TOTP verification required</Text>
            <Text size="xs" c="dimmed" mb="xs">
              Enter your 6-digit authenticator code to confirm emergency access.
            </Text>
            <PinInput
              length={6}
              type="number"
              value={mfaCode}
              onChange={setMfaCode}
              onComplete={setMfaCode}
              aria-label="TOTP code for break-glass confirmation"
            />
          </Box>
        )}

        <span id={confirmDescId} style={{ display: "none" }}>
          {reasonTooShort
            ? "Justification must be at least 20 characters."
            : needsMfa
            ? "Enter your 6-digit TOTP code to proceed."
            : ""}
        </span>

        <Group justify="flex-end">
          <Button variant="subtle" onClick={onClose}>Cancel</Button>
          <Button
            color="orange"
            loading={loading}
            onClick={onConfirm}
            disabled={confirmDisabled}
            aria-disabled={confirmDisabled}
            aria-describedby={confirmDisabled ? confirmDescId : undefined}
          >
            Confirm Break Glass
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}
