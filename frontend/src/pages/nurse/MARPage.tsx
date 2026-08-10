/**
 * MARPage — Medication Administration Record for nurses.
 * Displays patient medications grouped by patient and drug,
 * with dose checkboxes representing shift due times: 08:00, 12:00, 16:00, and 20:00.
 */

import {
  Box,
  Card,
  Group,
  Stack,
  Table,
  Text,
  ThemeIcon,
  Title,
  Checkbox,
} from "@mantine/core";
import { IconCheck, IconPill } from "@tabler/icons-react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import dayjs from "dayjs";
import { useMemo } from "react";
import { fetchMedAdmins, updateMedAdminStatus } from "@/api/endpoints";
import { notifications } from "@mantine/notifications";
import type { MedicationAdministration } from "@/types";

export function MARPage() {
  const queryClient = useQueryClient();

  const { data: medAdmins, isLoading } = useQuery({
    queryKey: ["mar-med-admins"],
    queryFn: () => fetchMedAdmins().then((r) => r.data),
    refetchInterval: 15_000,
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, status }: { id: number; status: string }) =>
      updateMedAdminStatus(id, status),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["mar-med-admins"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
    onError: () => {
      notifications.show({ color: "red", message: "Failed to update medication status." });
    },
  });

  const handleCheckboxToggle = (admin: MedicationAdministration) => {
    const isGiven = admin.status === "given";
    const newStatus = isGiven ? "due" : "given";
    
    updateMutation.mutate({ id: admin.id, status: newStatus });
    
    if (newStatus === "given") {
      const nowStr = dayjs().format("HH:mm");
      notifications.show({
        title: "Medication Administered",
        message: `Marked ${admin.prescription_drug_name} as GIVEN at ${nowStr} for ${admin.patient_name}.`,
        color: "green",
        icon: <IconCheck size={16} />,
      });
    } else {
      notifications.show({
        title: "Medication Reversed",
        message: `Reverted administration of ${admin.prescription_drug_name} for ${admin.patient_name}.`,
        color: "orange",
      });
    }
  };

  // Group by patient_nhid + prescription_drug_name + date
  const marRows = useMemo(() => {
    if (!medAdmins) return [];
    
    const groups: Record<string, {
      patientName: string;
      patientNhid: string;
      bedLabel: string;
      drugName: string;
      dosage: string;
      frequency: string;
      slots: Record<string, MedicationAdministration>;
    }> = {};

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
          slots: {},
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
      groups[groupKey].slots[matchedSlot] = admin;
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
            <Title order={2} style={{ fontSize: "20px", fontWeight: 500 }}>Medication Administration Record</Title>
            <Text size="xs" c="dimmed">
              Daily shift checklist · {shiftDueCount} doses pending · {shiftGivenCount} administered
            </Text>
          </Box>
        </Group>
      </Group>

      {/* Grid of Slots */}
      <Card withBorder radius="md" p={0} bg="var(--surface-2)">
        <Table.ScrollContainer minWidth={800}>
          <Table striped highlightOnHover>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Patient / Bed</Table.Th>
                <Table.Th>Medication</Table.Th>
                <Table.Th>Dose / Freq</Table.Th>
                <Table.Th style={{ textAlign: "center" }}>08:00</Table.Th>
                <Table.Th style={{ textAlign: "center" }}>12:00</Table.Th>
                <Table.Th style={{ textAlign: "center" }}>16:00</Table.Th>
                <Table.Th style={{ textAlign: "center" }}>20:00</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {isLoading && (
                <Table.Tr>
                  <Table.Td colSpan={7}><Text ta="center" c="dimmed" py="md">Loading MAR entries…</Text></Table.Td>
                </Table.Tr>
              )}
              {!isLoading && marRows.length === 0 && (
                <Table.Tr>
                  <Table.Td colSpan={7}><Text ta="center" c="dimmed" py="md">No medication administrations scheduled.</Text></Table.Td>
                </Table.Tr>
              )}
              {!isLoading && marRows.map((r, idx) => (
                <Table.Tr key={`${r.patientNhid}-${r.drugName}-${idx}`}>
                  <Table.Td>
                    <Text size="sm" fw={600}>{r.patientName}</Text>
                    <Text size="xs" c="dimmed">{r.bedLabel}</Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm" fw={600} c="medsync">{r.drugName}</Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="xs">{r.dosage}</Text>
                    <Text size="10px" c="dimmed">{r.frequency}</Text>
                  </Table.Td>
                  
                  {/* Slots */}
                  {["08:00", "12:00", "16:00", "20:00"].map((slot) => {
                    const admin = r.slots[slot];

                    if (!admin) {
                      return (
                        <Table.Td key={slot} style={{ textAlign: "center", verticalAlign: "middle" }}>
                          <Text size="xs" c="var(--text-muted)">—</Text>
                        </Table.Td>
                      );
                    }

                    const isGiven = admin.status === "given";
                    const adminTime = admin.administered_time ? dayjs(admin.administered_time).format("HH:mm") : null;

                    return (
                      <Table.Td key={slot} style={{ textAlign: "center", verticalAlign: "middle" }}>
                        <Stack gap={2} align="center">
                          <Checkbox
                            checked={isGiven}
                            color="green"
                            onChange={() => handleCheckboxToggle(admin)}
                            disabled={updateMutation.isPending && updateMutation.variables?.id === admin.id}
                          />
                          {isGiven && (
                            <Text size="9px" c="green" fw={700}>
                              Given {adminTime}
                            </Text>
                          )}
                          {admin.status === "missed" && (
                            <Text size="9px" c="red" fw={700}>
                              Missed
                            </Text>
                          )}
                        </Stack>
                      </Table.Td>
                    );
                  })}
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      </Card>
    </Stack>
  );
}
