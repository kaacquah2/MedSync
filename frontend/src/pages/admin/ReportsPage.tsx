import {
  Box,
  Button,
  Card,
  Group,
  SimpleGrid,
  Stack,
  Table,
  Text,
  ThemeIcon,
  Title,
  Select,
} from "@mantine/core";
import { DatePickerInput } from "@mantine/dates";
import {
  IconChartBar,
  IconDownload,
  IconPrinter,
} from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import dayjs from "dayjs";
import { useState, useMemo } from "react";
import { fetchDashboard } from "@/api/endpoints";
import { notifications } from "@mantine/notifications";

export function ReportsPage() {
  const [dateRange, setDateRange] = useState<[Date | null, Date | null]>([
    dayjs().subtract(14, "days").toDate(),
    new Date()
  ]);
  const [encounterType, setEncounterType] = useState<string | null>(null);
  const [doctorFilter, setDoctorFilter] = useState<string | null>(null);

  const { data } = useQuery({
    queryKey: ["reports-dashboard"],
    queryFn:  () => fetchDashboard().then((r) => r.data),
    staleTime: 60_000,
  });

  const encounters = useMemo(() => data?.recent_encounters || [], [data]);

  // Compute list of unique doctors for filter dropdown
  const doctorsList = useMemo(() => {
    const doctors = new Set<string>();
    encounters.forEach((e) => {
      const docName = e.created_by?.full_name;
      if (docName) doctors.add(docName);
    });
    return Array.from(doctors).map(name => ({ value: name, label: name }));
  }, [encounters]);

  // Filter encounters reactively on the frontend
  const filteredEncounters = useMemo(() => {
    return encounters.filter((e) => {
      if (dateRange[0] && dayjs(e.created_at).isBefore(dayjs(dateRange[0]).startOf("day"))) return false;
      if (dateRange[1] && dayjs(e.created_at).isAfter(dayjs(dateRange[1]).endOf("day"))) return false;
      if (encounterType && e.encounter_type !== encounterType) return false;
      if (doctorFilter) {
        const docName = e.created_by?.full_name;
        if (docName !== doctorFilter) return false;
      }
      return true;
    });
  }, [encounters, dateRange, encounterType, doctorFilter]);

  // Dynamic Summaries
  const summaryStats = useMemo(() => {
    const total = filteredEncounters.length;
    const types: Record<string, number> = {};
    const docs: Record<string, number> = {};

    filteredEncounters.forEach((e) => {
      const typeDisplay = e.encounter_type_display || e.encounter_type;
      types[typeDisplay] = (types[typeDisplay] || 0) + 1;

      const docName = e.created_by?.full_name || "Unknown Doctor";
      docs[docName] = (docs[docName] || 0) + 1;
    });

    return { total, types, docs };
  }, [filteredEncounters]);

  // Export CSV Action
  function exportCSV() {
    if (!filteredEncounters.length) {
      notifications.show({
        title: "Export Failed",
        message: "No data available in the current report filter selection.",
        color: "red",
      });
      return;
    }
    const rows = [
      ["NHID", "Patient Name", "Type", "Hospital", "Date", "Doctor"],
      ...filteredEncounters.map((e) => [
        e.patient_nhid,
        e.patient_name,
        e.encounter_type_display,
        e.created_at_hospital?.name ?? "",
        dayjs(e.created_at).format("YYYY-MM-DD"),
        e.created_by?.full_name || "",
      ]),
    ];
    const csv = rows.map((r) => r.map((c) => `"${c}"`).join(",")).join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement("a");
    a.href     = url;
    a.download = `mEd_report_${dayjs().format("YYYY-MM-DD")}.csv`;
    a.click();
    URL.revokeObjectURL(url);
    notifications.show({
      title: "Export Success",
      message: "CSV report exported successfully.",
      color: "green",
    });
  }

  // Print PDF Action
  function exportPDF() {
    window.print();
  }

  return (
    <Stack gap="lg" className="print-container">
      {/* Page Header */}
      <Group justify="space-between" align="center" className="no-print">
        <Group gap="xs">
          <ThemeIcon size={36} color="medsync" variant="light" radius="md">
            <IconChartBar size={20} />
          </ThemeIcon>
          <Box>
            <Title order={2} style={{ fontSize: "20px", fontWeight: 500 }}>Reports & Operations</Title>
            <Text size="xs" c="dimmed">
              Recent encounter activity visible to your role — export as CSV or print
            </Text>
          </Box>
        </Group>
        <Group gap="xs">
          <Button leftSection={<IconPrinter size={16} />} variant="subtle" size="sm" onClick={exportPDF} color="gray">
            Print report
          </Button>
          <Button leftSection={<IconDownload size={16} />} variant="light" size="sm" onClick={exportCSV} color="medsync">
            Export CSV
          </Button>
        </Group>
      </Group>

      {/* Filters Bar */}
      <Card withBorder radius="md" p="md" className="no-print" bg="var(--surface-2)">
        <SimpleGrid cols={{ base: 1, sm: 4 }} spacing="md">
          <DatePickerInput
            type="range"
            label="Date range"
            placeholder="From — To"
            value={dateRange}
            onChange={setDateRange}
            clearable
          />

          <Select
            label="Encounter type"
            placeholder="All types"
            data={[
              { value: "OPD", label: "Outpatient" },
              { value: "IPD", label: "Inpatient" },
              { value: "EMRG", label: "Emergency" },
              { value: "FU", label: "Follow-up" },
            ]}
            value={encounterType}
            onChange={setEncounterType}
            clearable
          />

          <Select
            label="Doctor"
            placeholder="All doctors"
            data={doctorsList}
            value={doctorFilter}
            onChange={setDoctorFilter}
            clearable
          />
        </SimpleGrid>
      </Card>

      {/* Report Summary Stats */}
      <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="md">
        <Card withBorder radius="md" p="md" bg="var(--surface-2)">
          <Text size="xs" tt="uppercase" fw={700} c="dimmed">Total Encounters</Text>
          <Text size="xl" fw={800}>{summaryStats.total}</Text>
          <Text size="xs" c="dimmed" mt={4}>In selected range & filters</Text>
        </Card>

        <Card withBorder radius="md" p="md" bg="var(--surface-2)">
          <Text size="xs" tt="uppercase" fw={700} c="dimmed">Encounter Breakdown (Top Type)</Text>
          <Text size="xl" fw={800}>
            {Object.entries(summaryStats.types).sort((a, b) => b[1] - a[1])[0]?.[0] || "—"}
          </Text>
          <Text size="xs" c="dimmed" mt={4}>
            Count: {Object.entries(summaryStats.types).sort((a, b) => b[1] - a[1])[0]?.[1] || 0}
          </Text>
        </Card>

        <Card withBorder radius="md" p="md" bg="var(--surface-2)">
          <Text size="xs" tt="uppercase" fw={700} c="dimmed">Top Doctor (Visits)</Text>
          <Text size="xl" fw={800}>
            {Object.entries(summaryStats.docs).sort((a, b) => b[1] - a[1])[0]?.[0] || "—"}
          </Text>
          <Text size="xs" c="dimmed" mt={4}>
            Count: {Object.entries(summaryStats.docs).sort((a, b) => b[1] - a[1])[0]?.[1] || 0}
          </Text>
        </Card>
      </SimpleGrid>

      {/* Breakdown Tables */}
      <Card withBorder radius="md" p="md" bg="var(--surface-2)">
        <Text fw={600} size="sm" tt="uppercase" c="dimmed" mb="sm">Summary Breakdown</Text>
        <SimpleGrid cols={{ base: 1, md: 2 }} spacing="md">
          {/* By Type */}
          <Box>
            <Text fw={600} size="xs" mb="xs">By Encounter Type</Text>
            <Table striped>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Type</Table.Th>
                  <Table.Th>Visits</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {Object.entries(summaryStats.types).map(([key, val]) => (
                  <Table.Tr key={key}>
                    <Table.Td>{key}</Table.Td>
                    <Table.Td fw={600}>{val}</Table.Td>
                  </Table.Tr>
                ))}
                {Object.keys(summaryStats.types).length === 0 && (
                  <Table.Tr><Table.Td colSpan={2} c="dimmed" style={{ textAlign: "center" }}>No records</Table.Td></Table.Tr>
                )}
              </Table.Tbody>
            </Table>
          </Box>

          {/* By Doctor */}
          <Box>
            <Text fw={600} size="xs" mb="xs">By Doctor</Text>
            <Table striped>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Doctor</Table.Th>
                  <Table.Th>Visits</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {Object.entries(summaryStats.docs).map(([key, val]) => (
                  <Table.Tr key={key}>
                    <Table.Td>{key}</Table.Td>
                    <Table.Td fw={600}>{val}</Table.Td>
                  </Table.Tr>
                ))}
                {Object.keys(summaryStats.docs).length === 0 && (
                  <Table.Tr><Table.Td colSpan={2} c="dimmed" style={{ textAlign: "center" }}>No records</Table.Td></Table.Tr>
                )}
              </Table.Tbody>
            </Table>
          </Box>
        </SimpleGrid>
      </Card>

      {/* Details Table */}
      <Card withBorder radius="md" p="lg" bg="var(--surface-2)">
        <Text fw={600} size="sm" tt="uppercase" c="dimmed" mb="md">Filtered Encounters List</Text>
        {filteredEncounters.length === 0 ? (
          <div className="empty-state">
            <IconChartBar size={32} color="var(--text-muted)" />
            <h4>No encounters yet</h4>
            <p>No encounters match the selected filters or date range.</p>
          </div>
        ) : (
          <Table.ScrollContainer minWidth={700}>
            <Table striped highlightOnHover>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>NHID</Table.Th>
                  <Table.Th>Patient Name</Table.Th>
                  <Table.Th>Type</Table.Th>
                  <Table.Th>Doctor</Table.Th>
                  <Table.Th>Date</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {filteredEncounters.map((e) => (
                  <Table.Tr key={e.id}>
                    <Table.Td><Text size="xs" ff="monospace">{e.patient_nhid}</Text></Table.Td>
                    <Table.Td fw={500}>{e.patient_name}</Table.Td>
                    <Table.Td>{e.encounter_type_display}</Table.Td>
                    <Table.Td>{e.created_by?.full_name || "—"}</Table.Td>
                    <Table.Td><Text size="xs" c="dimmed">{dayjs(e.created_at).format("DD MMM YYYY")}</Text></Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        )}
      </Card>
    </Stack>
  );
}
