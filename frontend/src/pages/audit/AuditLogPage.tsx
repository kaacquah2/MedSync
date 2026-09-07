import {
  Badge,
  Box,
  Button,
  Group,
  Pagination,
  Paper,
  ScrollArea,
  Select,
  Stack,
  Switch,
  Table,
  Text,
  TextInput,
  Title,
  ThemeIcon,
  Anchor,
} from "@mantine/core";
import { DatePickerInput } from "@mantine/dates";
import { IconFilter, IconRefresh, IconShieldLock, IconDownload, IconChevronDown, IconChevronUp } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import dayjs from "dayjs";
import { useState } from "react";
import { Link } from "react-router-dom";
import { fetchAuditActions, fetchAuditLog } from "@/api/endpoints";
import { notifications } from "@mantine/notifications";

const ACTION_COLORS: Record<string, string> = {
  LOGIN:               "green",
  LOGOUT:              "gray",
  VIEW_PATIENT:        "blue",
  CREATE_PATIENT:      "teal",
  UPDATE_PATIENT:      "cyan",
  CREATE_ENCOUNTER:    "blue",
  VIEW_ENCOUNTER:      "blue",
  CREATE_DIAGNOSIS:    "indigo",
  CREATE_PRESCRIPTION: "violet",
  CREATE_LAB_RESULT:   "purple",
  ACCESS_DENIED:       "red",
  BREAK_GLASS:         "orange",
  MFA_ENROLLED:        "green",
  MFA_VERIFIED:        "green",
  MFA_REMOVED:         "orange",
  STAFF_DEACTIVATED:   "red",
  STAFF_ACTIVATED:     "green",
  STAFF_CREATED:       "teal",
  STAFF_UPDATED:       "cyan",
  SESSIONS_REVOKED:    "red",
};

export function AuditLogPage() {
  const [page,       setPage]       = useState(1);
  const [action,     setAction]     = useState("");
  const [nhid,       setNhid]       = useState("");
  const [actor,      setActor]      = useState("");
  const [crossOnly,  setCrossOnly]  = useState(false);
  const [dateRange,  setDateRange]  = useState<[Date | null, Date | null]>([null, null]);
  const [submitted,  setSubmitted]  = useState<Record<string, string>>({});
  const [expandedRow, setExpandedRow] = useState<number | null>(null);

  const { data: actions } = useQuery({
    queryKey: ["audit-actions"],
    queryFn:  () => fetchAuditActions().then((r) => r.data),
    staleTime: Infinity,
  });

  const { data, isLoading, refetch } = useQuery({
    queryKey: ["audit", submitted, page],
    queryFn:  () => fetchAuditLog({ ...submitted, page: String(page) }).then((r) => r.data),
  });

  function applyFilters() {
    const f: Record<string, string> = {};
    if (action)    f.action = action;
    if (nhid)      f.nhid = nhid;
    if (actor)     f.actor = actor;
    if (crossOnly) f.cross_hospital = "true";
    if (dateRange[0]) f.start_date = dayjs(dateRange[0]).format("YYYY-MM-DD");
    if (dateRange[1]) f.end_date = dayjs(dateRange[1]).format("YYYY-MM-DD");
    setSubmitted(f);
    setPage(1);
  }

  // Export CSV function
  function exportCSV() {
    const results = data?.results || [];
    if (!results.length) {
      notifications.show({
        title: "Export Failed",
        message: "No audit logs available to export in current view.",
        color: "red",
      });
      return;
    }
    const rows = [
      ["Timestamp", "Actor", "Role", "Hospital", "Action", "Patient NHID", "Cross-Hospital", "IP Address", "Details"],
      ...results.map((e) => [
        dayjs(e.timestamp).format("YYYY-MM-DD HH:mm:ss"),
        e.actor_username || "",
        e.actor_role,
        e.actor_hospital,
        e.action_display,
        e.patient_nhid || "",
        e.is_cross_hospital ? "YES" : "NO",
        e.ip_address || "",
        JSON.stringify(e.extra || {}),
      ]),
    ];
    const csv = rows.map((r) => r.map((c) => `"${c}"`).join(",")).join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement("a");
    a.href     = url;
    a.download = `mEd_audit_log_${dayjs().format("YYYY-MM-DD")}.csv`;
    a.click();
    URL.revokeObjectURL(url);
    notifications.show({
      title: "Export Success",
      message: "Audit logs exported successfully.",
      color: "green",
    });
  }

  const totalPages = data ? Math.ceil(data.count / 50) : 1;

  function toggleRow(id: number) {
    setExpandedRow(prev => (prev === id ? null : id));
  }

  return (
    <Stack gap="lg">
      <Group justify="space-between">
        <Group>
          <ThemeIcon size={36} color="medsync" variant="light" radius="md">
            <IconShieldLock size={20} />
          </ThemeIcon>
          <Title order={2} style={{ fontSize: "20px", fontWeight: 500 }}>System Audit Logs</Title>
        </Group>
        <Group gap="xs">
          <Button variant="light" leftSection={<IconDownload size={14} />} onClick={exportCSV} color="medsync">
            Export CSV
          </Button>
          <Badge color="red" size="lg">{data?.count ?? "…"} entries</Badge>
        </Group>
      </Group>

      {/* Filters */}
      <Paper withBorder p="md" radius="md" bg="var(--surface-2)">
        <Group align="flex-end" gap="sm" wrap="wrap">
          <DatePickerInput
            type="range"
            label="Date range"
            placeholder="From — To"
            value={dateRange}
            onChange={setDateRange}
            w={200}
            clearable
          />
          <Select
            label="Action"
            data={[{ value: "", label: "All actions" }, ...(actions ?? []).map((a) => ({ value: a.value, label: a.label }))]}
            value={action}
            onChange={(v) => setAction(v ?? "")}
            clearable
            w={200}
          />
          <TextInput
            label="Patient NHID"
            placeholder="NHID-XXXXXXXX"
            value={nhid}
            onChange={(e) => setNhid(e.currentTarget.value)}
            w={160}
          />
          <TextInput
            label="Actor username"
            placeholder="username"
            value={actor}
            onChange={(e) => setActor(e.currentTarget.value)}
            w={150}
          />
          <Switch
            label="Cross-hospital"
            checked={crossOnly}
            onChange={(e) => setCrossOnly(e.currentTarget.checked)}
            mb={10}
          />
          <Button
            leftSection={<IconFilter size={16} />}
            onClick={applyFilters}
          >
            Apply Filters
          </Button>
          <Button
            variant="subtle"
            leftSection={<IconRefresh size={16} />}
            onClick={() => refetch()}
            color="gray"
          >
            Refresh
          </Button>
        </Group>
      </Paper>

      {/* Table */}
      <ScrollArea>
        <Table striped highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th style={{ width: 40 }}></Table.Th>
              <Table.Th>Timestamp</Table.Th>
              <Table.Th>Actor</Table.Th>
              <Table.Th>Role / Hospital</Table.Th>
              <Table.Th>Action</Table.Th>
              <Table.Th>Patient</Table.Th>
              <Table.Th>Cross-Hospital</Table.Th>
              <Table.Th>IP Address</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {isLoading && (
              <Table.Tr>
                <Table.Td colSpan={8}><Text ta="center" c="dimmed" py="xl">Loading…</Text></Table.Td>
              </Table.Tr>
            )}
            {!isLoading && (data?.results ?? []).length === 0 && (
              <Table.Tr>
                <Table.Td colSpan={8}><Text ta="center" c="dimmed" py="xl">No audit logs found.</Text></Table.Td>
              </Table.Tr>
            )}
            {(data?.results ?? []).map((entry) => {
              const isExpanded = expandedRow === entry.id;
              return (
                <>
                  <Table.Tr
                    key={entry.id}
                    bg={entry.is_cross_hospital ? "var(--bg-amber)" : undefined}
                    onClick={() => toggleRow(entry.id)}
                    style={{ cursor: "pointer" }}
                  >
                    <Table.Td onClick={(e) => e.stopPropagation()}>
                      <Button size="xs" variant="subtle" color="gray" p={0} onClick={() => toggleRow(entry.id)}>
                        {isExpanded ? <IconChevronUp size={16} /> : <IconChevronDown size={16} />}
                      </Button>
                    </Table.Td>
                    <Table.Td>
                      <Text size="sm" ff="monospace">{dayjs(entry.timestamp).format("DD MMM HH:mm:ss")}</Text>
                    </Table.Td>
                    <Table.Td>
                      <Text size="sm" fw={600}>{entry.actor_username || "—"}</Text>
                    </Table.Td>
                    <Table.Td>
                      <Text size="xs" c="var(--text-secondary)">{entry.actor_role}</Text>
                      <Text size="xs" c="var(--text-muted)">{entry.actor_hospital}</Text>
                    </Table.Td>
                    <Table.Td>
                      <Badge
                        color={ACTION_COLORS[entry.action] ?? "gray"}
                        variant="light"
                        size="sm"
                      >
                        {entry.action_display}
                      </Badge>
                    </Table.Td>
                    <Table.Td onClick={(e) => e.stopPropagation()}>
                      {entry.patient_nhid ? (
                        <Anchor
                          component={Link}
                          to={`/patients/${entry.patient_nhid}`}
                          style={{ fontFamily: "monospace", fontSize: 12, fontWeight: 600 }}
                        >
                          {entry.patient_nhid}
                        </Anchor>
                      ) : "—"}
                    </Table.Td>
                    <Table.Td>
                      {entry.is_cross_hospital && (
                        <Badge color="red" size="xs">YES ⚠</Badge>
                      )}
                    </Table.Td>
                    <Table.Td>
                      <Text size="xs" ff="monospace" c="var(--text-muted)">{entry.ip_address ?? "—"}</Text>
                    </Table.Td>
                  </Table.Tr>
                  
                  {isExpanded && (
                    <Table.Tr key={`${entry.id}-detail`} bg="var(--surface-0)">
                      <Table.Td colSpan={8}>
                        <Box p="md">
                          <Text fw={600} size="xs" mb="xs" c="var(--text-primary)">Extended Action Details:</Text>
                          <Table withTableBorder withColumnBorders style={{ backgroundColor: "var(--surface-2)" }}>
                            <Table.Tbody>
                              <Table.Tr>
                                <Table.Td fw={500} w={120}>Target Resource</Table.Td>
                                <Table.Td>{entry.target_type} ({entry.target_id || "N/A"})</Table.Td>
                              </Table.Tr>
                              {Object.entries(entry.extra || {}).map(([key, val]) => (
                                <Table.Tr key={key}>
                                  <Table.Td fw={500} style={{ textTransform: "capitalize" }}>{key.replace(/_/g, " ")}</Table.Td>
                                  <Table.Td>{typeof val === "object" ? JSON.stringify(val) : String(val)}</Table.Td>
                                </Table.Tr>
                              ))}
                            </Table.Tbody>
                          </Table>
                        </Box>
                      </Table.Td>
                    </Table.Tr>
                  )}
                </>
              );
            })}
          </Table.Tbody>
        </Table>
      </ScrollArea>

      {totalPages > 1 && (
        <Pagination total={totalPages} value={page} onChange={setPage} />
      )}
    </Stack>
  );
}
