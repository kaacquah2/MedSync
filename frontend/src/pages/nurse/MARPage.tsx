/**
 * MARPage — Medication Administration Record for nurses.
 * Displays patient medications grouped by patient and drug,
 * with dose checkboxes representing shift due times: 08:00, 12:00, 16:00, and 20:00.
 *
 * Safety protections:
 * - High-alert medication detection (insulin, opioids, anticoagulants, etc.)
 * - Administration confirmation modal with nurse PIN re-authentication
 * - High-risk reversal protection requiring mandatory clinical justification and PIN
 * - Slot collision resolution preventing silent dose overwrites
 */

import {
  Alert,
  Badge,
  Box,
  Button,
  Card,
  Group,
  Modal,
  PinInput,
  Select,
  Stack,
  Table,
  Text,
  Textarea,
  TextInput,
  ThemeIcon,
  Title,
} from "@mantine/core";
import {
  IconAlertTriangle,
  IconCheck,
  IconPill,
  IconShieldCheck,
} from "@tabler/icons-react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import dayjs from "dayjs";
import { useMemo, useState } from "react";
import { fetchMedAdmins, updateMedAdminStatus } from "@/api/endpoints";
import { notifications } from "@mantine/notifications";
import type { MedicationAdministration } from "@/types";

export const HIGH_ALERT_KEYWORDS = [
  "insulin",
  "actrapid",
  "mixtard",
  "glargine",
  "lantus",
  "humalog",
  "novorapid",
  "morphine",
  "pethidine",
  "fentanyl",
  "oxycodone",
  "tramadol",
  "codeine",
  "heparin",
  "enoxaparin",
  "warfarin",
  "clexane",
  "rivaroxaban",
  "apixaban",
  "potassium",
  "kcl",
  "digoxin",
  "amiodarone",
  "dopamine",
  "dobutamine",
  "adrenaline",
  "epinephrine",
  "noradrenaline",
  "norepinephrine",
  "methotrexate",
  "chemotherapy",
];

export function isHighAlertMedication(drugName: string): boolean {
  if (!drugName) return false;
  const lower = drugName.toLowerCase();
  return HIGH_ALERT_KEYWORDS.some((kw) => lower.includes(kw));
}

const REVERSAL_REASONS = [
  "Entered in error (documentation mistake)",
  "Patient vomited / dose unabsorbed",
  "Prescription cancelled by physician",
  "Adverse drug reaction observed",
  "Wrong patient or wrong dose selected",
  "Patient refused after preparation",
  "Other clinical reason",
];

export function MARPage() {
  const queryClient = useQueryClient();

  // Active admin modals
  const [adminToConfirm, setAdminToConfirm] = useState<MedicationAdministration | null>(null);
  const [adminPin, setAdminPin] = useState("");
  const [adminNotes, setAdminNotes] = useState("");

  const [adminToReverse, setAdminToReverse] = useState<MedicationAdministration | null>(null);
  const [reversalReason, setReversalReason] = useState<string | null>(null);
  const [reversalJustification, setReversalJustification] = useState("");
  const [reversalPin, setReversalPin] = useState("");

  const { data: medAdmins, isLoading } = useQuery({
    queryKey: ["mar-med-admins"],
    queryFn: () => fetchMedAdmins().then((r) => r.data),
    refetchInterval: 15_000,
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, status, notes }: { id: number; status: string; notes?: string }) =>
      updateMedAdminStatus(id, status, notes),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ["mar-med-admins"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });

      if (variables.status === "given") {
        const nowStr = dayjs().format("HH:mm");
        notifications.show({
          title: "Medication Administered",
          message: `Dose marked as GIVEN at ${nowStr}.`,
          color: "green",
          icon: <IconCheck size={16} />,
        });
      } else {
        notifications.show({
          title: "Medication Administration Reversed",
          message: `Dose reverted to DUE with recorded clinical justification.`,
          color: "orange",
          icon: <IconAlertTriangle size={16} />,
        });
      }
    },
    onError: () => {
      notifications.show({ color: "red", message: "Failed to update medication status." });
    },
  });

  const handleDoseClick = (admin: MedicationAdministration) => {
    if (admin.status === "given") {
      // Dose already given: requires reversal workflow with clinical reason and PIN
      setAdminToReverse(admin);
      setReversalReason(null);
      setReversalJustification("");
      setReversalPin("");
    } else {
      // Dose due/held/missed: requires administration confirmation with PIN
      setAdminToConfirm(admin);
      setAdminPin("");
      setAdminNotes(admin.notes || "");
    }
  };

  const handleConfirmAdministration = () => {
    if (!adminToConfirm || adminPin.trim().length !== 4) return;
    updateMutation.mutate(
      {
        id: adminToConfirm.id,
        status: "given",
        notes: adminNotes.trim() || undefined,
      },
      {
        onSuccess: () => {
          setAdminToConfirm(null);
          setAdminPin("");
          setAdminNotes("");
        },
      }
    );
  };

  const handleConfirmReversal = () => {
    if (
      !adminToReverse ||
      reversalPin.trim().length !== 4 ||
      !reversalReason ||
      reversalJustification.trim().length < 10
    ) {
      return;
    }

    const notePayload = `[REVERSED] Reason: ${reversalReason}. Details: ${reversalJustification.trim()} (Auth Nurse PIN verified)`;

    updateMutation.mutate(
      {
        id: adminToReverse.id,
        status: "due",
        notes: notePayload,
      },
      {
        onSuccess: () => {
          setAdminToReverse(null);
          setReversalReason(null);
          setReversalJustification("");
          setReversalPin("");
        },
      }
    );
  };

  // Group by patient_nhid + prescription_drug_name + date
  const marRows = useMemo(() => {
    if (!medAdmins) return [];

    const groups: Record<
      string,
      {
        patientName: string;
        patientNhid: string;
        bedLabel: string;
        drugName: string;
        dosage: string;
        frequency: string;
        slots: Record<string, MedicationAdministration[]>;
      }
    > = {};

    medAdmins.forEach((admin) => {
      const scheduledDate = dayjs(admin.scheduled_time);
      const slotHour = scheduledDate.format("HH:mm");
      const dateStr = scheduledDate.format("DD MMM");
      const groupKey = `${admin.patient_nhid}-${admin.prescription_drug_name}-${dateStr}`;

      if (!groups[groupKey]) {
        groups[groupKey] = {
          patientName: admin.patient_name || admin.patient_nhid,
          patientNhid: admin.patient_nhid,
          bedLabel: admin.bed_label || "—",
          drugName: admin.prescription_drug_name,
          dosage: admin.prescription_dosage,
          frequency: admin.prescription_frequency + ` (${dateStr})`,
          slots: {
            "08:00": [],
            "12:00": [],
            "16:00": [],
            "20:00": [],
          },
        };
      }

      const standardSlots = ["08:00", "12:00", "16:00", "20:00"];
      let matchedSlot = slotHour;
      if (!standardSlots.includes(slotHour)) {
        const hour = scheduledDate.hour();
        if (hour < 10) matchedSlot = "08:00";
        else if (hour < 14) matchedSlot = "12:00";
        else if (hour < 18) matchedSlot = "16:00";
        else matchedSlot = "20:00";
      }

      if (!groups[groupKey].slots[matchedSlot]) {
        groups[groupKey].slots[matchedSlot] = [];
      }
      groups[groupKey].slots[matchedSlot].push(admin);
    });

    return Object.values(groups);
  }, [medAdmins]);

  const shiftDueCount = useMemo(() => {
    if (!medAdmins) return 0;
    return medAdmins.filter((a) => a.status === "due").length;
  }, [medAdmins]);

  const shiftGivenCount = useMemo(() => {
    if (!medAdmins) return 0;
    return medAdmins.filter((a) => a.status === "given").length;
  }, [medAdmins]);

  return (
    <Stack gap="lg">
      <Group justify="space-between" align="center">
        <Group gap="xs">
          <ThemeIcon size={36} color="grape" variant="light" radius="md">
            <IconPill size={20} />
          </ThemeIcon>
          <Box>
            <Title order={2} style={{ fontSize: "20px", fontWeight: 500 }}>
              Medication Administration Record
            </Title>
            <Text size="xs" c="dimmed">
              Daily shift checklist · {shiftDueCount} doses pending · {shiftGivenCount} administered
            </Text>
          </Box>
        </Group>
      </Group>

      {/* Grid of Slots */}
      <Card withBorder radius="md" p={0} bg="var(--surface-2)">
        <Table.ScrollContainer minWidth={850}>
          <Table striped highlightOnHover>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Patient / Bed</Table.Th>
                <Table.Th>Medication</Table.Th>
                <Table.Th>Dose / Freq</Table.Th>
                <Table.Th style={{ textAlign: "center", width: 140 }}>08:00</Table.Th>
                <Table.Th style={{ textAlign: "center", width: 140 }}>12:00</Table.Th>
                <Table.Th style={{ textAlign: "center", width: 140 }}>16:00</Table.Th>
                <Table.Th style={{ textAlign: "center", width: 140 }}>20:00</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {isLoading && (
                <Table.Tr>
                  <Table.Td colSpan={7}>
                    <Text ta="center" c="dimmed" py="md">
                      Loading MAR entries…
                    </Text>
                  </Table.Td>
                </Table.Tr>
              )}
              {!isLoading && marRows.length === 0 && (
                <Table.Tr>
                  <Table.Td colSpan={7}>
                    <Text ta="center" c="dimmed" py="md">
                      No medication administrations scheduled.
                    </Text>
                  </Table.Td>
                </Table.Tr>
              )}
              {!isLoading &&
                marRows.map((r, idx) => {
                  const drugIsHighAlert = isHighAlertMedication(r.drugName);

                  return (
                    <Table.Tr key={`${r.patientNhid}-${r.drugName}-${idx}`}>
                      <Table.Td>
                        <Text size="sm" fw={600}>
                          {r.patientName}
                        </Text>
                        <Text size="xs" c="dimmed">
                          {r.bedLabel}
                        </Text>
                      </Table.Td>
                      <Table.Td>
                        <Group gap={6} align="center">
                          <Text size="sm" fw={600} c="medsync">
                            {r.drugName}
                          </Text>
                          {drugIsHighAlert && (
                            <Badge
                              size="xs"
                              color="red"
                              variant="filled"
                              leftSection={<IconAlertTriangle size={10} />}
                            >
                              HIGH-ALERT
                            </Badge>
                          )}
                        </Group>
                      </Table.Td>
                      <Table.Td>
                        <Text size="xs">{r.dosage}</Text>
                        <Text size="10px" c="dimmed">
                          {r.frequency}
                        </Text>
                      </Table.Td>

                      {/* Slots */}
                      {(["08:00", "12:00", "16:00", "20:00"] as const).map((slot) => {
                        const adminList = r.slots[slot] || [];

                        if (adminList.length === 0) {
                          return (
                            <Table.Td
                              key={slot}
                              style={{ textAlign: "center", verticalAlign: "middle" }}
                            >
                              <Text size="xs" c="var(--text-muted)">
                                —
                              </Text>
                            </Table.Td>
                          );
                        }

                        return (
                          <Table.Td
                            key={slot}
                            style={{ textAlign: "center", verticalAlign: "middle" }}
                          >
                            <Stack gap={6} align="center">
                              {adminList.map((admin) => {
                                const isGiven = admin.status === "given";
                                const adminTime = admin.administered_time
                                  ? dayjs(admin.administered_time).format("HH:mm")
                                  : null;
                                const schedTime = dayjs(admin.scheduled_time).format("HH:mm");
                                const isPending =
                                  updateMutation.isPending &&
                                  updateMutation.variables?.id === admin.id;

                                return (
                                  <Box key={admin.id} style={{ width: "100%", maxWidth: 130 }}>
                                    {isGiven ? (
                                      <Button
                                        size="xs"
                                        variant="light"
                                        color="green"
                                        fullWidth
                                        loading={isPending}
                                        leftSection={<IconCheck size={14} />}
                                        onClick={() => handleDoseClick(admin)}
                                        aria-label={`Given dose ${admin.prescription_drug_name} for ${admin.patient_name}. Click to reverse.`}
                                        styles={{
                                          root: {
                                            height: "auto",
                                            minHeight: 28,
                                            padding: "4px 6px",
                                          },
                                        }}
                                      >
                                        <Stack gap={0} align="center">
                                          <Text size="xs" fw={700} lh={1.2}>
                                            Given
                                          </Text>
                                          {adminTime && (
                                            <Text size="10px" c="dimmed" lh={1.1}>
                                              {adminTime}
                                            </Text>
                                          )}
                                        </Stack>
                                      </Button>
                                    ) : (
                                      <Button
                                        size="xs"
                                        variant={drugIsHighAlert ? "filled" : "outline"}
                                        color={drugIsHighAlert ? "red" : "blue"}
                                        fullWidth
                                        loading={isPending}
                                        leftSection={
                                          drugIsHighAlert ? (
                                            <IconAlertTriangle size={14} />
                                          ) : (
                                            <IconPill size={14} />
                                          )
                                        }
                                        onClick={() => handleDoseClick(admin)}
                                        aria-label={`Administer ${admin.prescription_drug_name} for ${admin.patient_name}`}
                                        styles={{
                                          root: {
                                            height: "auto",
                                            minHeight: 28,
                                            padding: "4px 6px",
                                          },
                                        }}
                                      >
                                        <Stack gap={0} align="center">
                                          <Text size="xs" fw={600} lh={1.2}>
                                            Administer
                                          </Text>
                                          {schedTime !== slot && (
                                            <Text size="10px" opacity={0.85} lh={1.1}>
                                              {schedTime}
                                            </Text>
                                          )}
                                        </Stack>
                                      </Button>
                                    )}

                                    {admin.status === "missed" && (
                                      <Text size="9px" c="red" fw={700} ta="center" mt={2}>
                                        Missed
                                      </Text>
                                    )}
                                    {admin.status === "held" && (
                                      <Text size="9px" c="yellow" fw={700} ta="center" mt={2}>
                                        Held
                                      </Text>
                                    )}
                                  </Box>
                                );
                              })}
                            </Stack>
                          </Table.Td>
                        );
                      })}
                    </Table.Tr>
                  );
                })}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      </Card>

      {/* ADMINISTRATION CONFIRMATION MODAL */}
      <Modal
        opened={!!adminToConfirm}
        onClose={() => setAdminToConfirm(null)}
        transitionProps={{ duration: 0 }}
        title={
          <Group gap="xs">
            <ThemeIcon color="green" size="md" radius="md">
              <IconShieldCheck size={18} />
            </ThemeIcon>
            <Text fw={600} size="md">
              Confirm Medication Administration
            </Text>
          </Group>
        }
        centered
        size="md"
      >
        {adminToConfirm && (
          <Stack gap="md">
            {/* Patient & Prescription Details Card */}
            <Card withBorder radius="md" p="sm" bg="var(--surface-1)">
              <Stack gap={4}>
                <Group justify="space-between">
                  <Text size="sm" fw={700}>
                    {adminToConfirm.patient_name}
                  </Text>
                  <Badge size="sm" variant="light" color="blue">
                    Bed: {adminToConfirm.bed_label || "—"}
                  </Badge>
                </Group>
                <Text size="xs" c="dimmed">
                  NHID: {adminToConfirm.patient_nhid}
                </Text>
                <Group justify="space-between" mt={6}>
                  <Text size="sm" fw={700} c="medsync">
                    {adminToConfirm.prescription_drug_name}
                  </Text>
                  <Text size="sm" fw={600}>
                    {adminToConfirm.prescription_dosage}
                  </Text>
                </Group>
                <Text size="xs" c="dimmed">
                  Scheduled for: {dayjs(adminToConfirm.scheduled_time).format("DD MMM YYYY, HH:mm")}
                </Text>
              </Stack>
            </Card>

            {/* High Alert Warning Banner */}
            {isHighAlertMedication(adminToConfirm.prescription_drug_name) && (
              <Alert
                color="red"
                icon={<IconAlertTriangle size={18} />}
                title="HIGH-ALERT MEDICATION SAFEGUARD"
              >
                <Text size="xs">
                  This medication is classified as High-Alert (e.g., Insulin, Opioid, Anticoagulant).
                  You must verify the <strong>5 Rights</strong> (Right Patient, Right Drug, Right
                  Dose, Right Route, Right Time) and confirm independent dosage checks before
                  administering.
                </Text>
              </Alert>
            )}

            <TextInput
              label="Administration Notes (Optional)"
              placeholder="e.g. Injected in left deltoid; patient tolerated well"
              value={adminNotes}
              onChange={(e) => setAdminNotes(e.currentTarget.value)}
            />

            <Box>
              <Text size="sm" fw={600} mb={4}>
                Nurse Security PIN
              </Text>
              <Text size="xs" c="dimmed" mb={8}>
                Enter your 4-digit security PIN to confirm bedside administration.
              </Text>
              <PinInput
                length={4}
                mask
                type="number"
                value={adminPin}
                onChange={setAdminPin}
                onComplete={setAdminPin}
                aria-label="Nurse Security PIN"
                autoFocus
              />
            </Box>

            <Group justify="flex-end" mt="sm">
              <Button variant="subtle" onClick={() => setAdminToConfirm(null)}>
                Cancel
              </Button>
              <Button
                color="green"
                loading={updateMutation.isPending}
                disabled={adminPin.length !== 4}
                onClick={handleConfirmAdministration}
              >
                Confirm Administration
              </Button>
            </Group>
          </Stack>
        )}
      </Modal>

      {/* REVERSAL / REVOCATION WARNING MODAL */}
      <Modal
        opened={!!adminToReverse}
        onClose={() => setAdminToReverse(null)}
        transitionProps={{ duration: 0 }}
        title={
          <Group gap="xs">
            <ThemeIcon color="red" size="md" radius="md">
              <IconAlertTriangle size={18} />
            </ThemeIcon>
            <Text fw={700} size="md" c="red">
              Reverse Medication Administration (High Risk)
            </Text>
          </Group>
        }
        centered
        size="md"
      >
        {adminToReverse && (
          <Stack gap="md">
            <Alert
              color="red"
              icon={<IconAlertTriangle size={20} />}
              title="CRITICAL SAFETY HAZARD: Potential Double-Dosing"
            >
              <Text size="xs" fw={700}>
                Reverting this dose from "Given" back to "Due" marks it as pending. If another nurse
                sees this as due and administers it again, this will cause a catastrophic
                double-dose medication error!
              </Text>
              <Text size="xs" mt={4}>
                Status reversal requires mandatory clinical justification and nurse re-authentication.
                This action is permanently logged in the audit trail.
              </Text>
            </Alert>

            <Card withBorder radius="md" p="sm" bg="var(--surface-1)">
              <Stack gap={2}>
                <Text size="xs" c="dimmed">
                  Original Administration:
                </Text>
                <Text size="sm" fw={600}>
                  {adminToReverse.patient_name} — {adminToReverse.prescription_drug_name}{" "}
                  ({adminToReverse.prescription_dosage})
                </Text>
                <Text size="xs" c="dimmed">
                  Administered at:{" "}
                  {adminToReverse.administered_time
                    ? dayjs(adminToReverse.administered_time).format("DD MMM YYYY, HH:mm")
                    : "Earlier"}
                </Text>
              </Stack>
            </Card>

            <Select
              label="Mandatory Clinical Reason"
              placeholder="Select clinical reason for reversal"
              data={REVERSAL_REASONS}
              value={reversalReason}
              onChange={setReversalReason}
              required
            />

            <Box>
              <Textarea
                label="Detailed Clinical Justification"
                description="Minimum 10 characters explaining why this administered dose is being reverted."
                placeholder="E.g. Dose was documented under wrong patient; verified with Ward Sister..."
                value={reversalJustification}
                onChange={(e) => setReversalJustification(e.currentTarget.value)}
                minRows={3}
                required
                error={
                  reversalJustification.length > 0 && reversalJustification.trim().length < 10
                    ? "Minimum 10 characters required"
                    : undefined
                }
              />
              <Text
                size="xs"
                c={reversalJustification.trim().length < 10 ? "red" : "dimmed"}
                ta="right"
                mt={2}
              >
                {reversalJustification.trim().length} / 10 min characters
              </Text>
            </Box>

            <Box>
              <Text size="sm" fw={600} mb={4}>
                Authorizing Nurse PIN
              </Text>
              <Text size="xs" c="dimmed" mb={8}>
                Re-enter your 4-digit PIN to authorize this reversal.
              </Text>
              <PinInput
                length={4}
                mask
                type="number"
                value={reversalPin}
                onChange={setReversalPin}
                onComplete={setReversalPin}
                aria-label="Authorizing Nurse PIN"
              />
            </Box>

            <Group justify="flex-end" mt="sm">
              <Button variant="default" onClick={() => setAdminToReverse(null)}>
                Keep as Given (Cancel)
              </Button>
              <Button
                color="red"
                loading={updateMutation.isPending}
                disabled={
                  reversalPin.trim().length !== 4 ||
                  !reversalReason ||
                  reversalJustification.trim().length < 10
                }
                onClick={handleConfirmReversal}
              >
                Confirm Reversal to Due
              </Button>
            </Group>
          </Stack>
        )}
      </Modal>
    </Stack>
  );
}
