/**
 * Doctor Worklist — dense, scannable list of active patients and encounters.
 */

import {
  Anchor,
  Badge,
  Box,
  Button,
  Group,
  Skeleton,
  Stack,
  Table,
  Text,
  ThemeIcon,
  Title,
  TextInput,
} from "@mantine/core";
import { IconSearch, IconPlus, IconStethoscope } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import dayjs from "dayjs";
import relativeTime from "dayjs/plugin/relativeTime";
import { useState, useMemo } from "react";
import { Link } from "react-router-dom";
import { fetchDashboard } from "@/api/endpoints";
import type { EncounterSummary } from "@/types";

dayjs.extend(relativeTime);

const ENCOUNTER_TYPE_COLORS: Record<string, string> = {
  OPD:  "blue",
  IPD:  "indigo",
  EMRG: "red",
  FU:   "teal",
  TM:   "violet",
};

export function WorklistPage() {
  const [search, setSearch] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["dashboard"],
    queryFn: () => fetchDashboard().then((r) => r.data),
    staleTime: 2 * 60 * 1000,
  });

  const encounters = data?.recent_encounters ?? [];

  const filtered = useMemo(() => {
    if (!search.trim()) return encounters;
    const q = search.toLowerCase();
    return encounters.filter(
      (e) =>
        e.patient_nhid.toLowerCase().includes(q) ||
        e.patient_name.toLowerCase().includes(q) ||
        e.encounter_type_display.toLowerCase().includes(q)
    );
  }, [encounters, search]);

  return (
    <Stack gap="lg">
      <Group justify="space-between">
        <Group gap="xs">
          <ThemeIcon size={36} color="medsync" variant="light" radius="md">
            <IconStethoscope size={20} />
          </ThemeIcon>
          <Title order={2}>My Worklist</Title>
        </Group>
        <Button
          component={Link}
          to="/patients"
          leftSection={<IconPlus size={16} />}
          variant="filled"
          size="sm"
        >
          Find Patient
        </Button>
      </Group>

      <TextInput
        placeholder="Filter by patient name or NHID…"
        leftSection={<IconSearch size={16} />}
        value={search}
        onChange={(e) => setSearch(e.currentTarget.value)}
        maw={400}
      />

      {isLoading ? (
        <Stack gap="xs">
          {[1, 2, 3, 4, 5].map((i) => <Skeleton key={i} height={52} radius="sm" />)}
        </Stack>
      ) : !filtered.length ? (
        <Box ta="center" py="xl">
          <Text c="dimmed" size="sm">
            {search ? "No encounters match your filter." : "No recent encounters. Your active patients will appear here."}
          </Text>
        </Box>
      ) : (
        <Table.ScrollContainer minWidth={700}>
          <Table striped highlightOnHover withTableBorder withColumnBorders>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Patient NHID</Table.Th>
                <Table.Th>Patient Name</Table.Th>
                <Table.Th>Type</Table.Th>
                <Table.Th>Hospital</Table.Th>
                <Table.Th>Flags</Table.Th>
                <Table.Th>Last Updated</Table.Th>
                <Table.Th>Actions</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {filtered.map((enc) => (
                <WorklistRow key={enc.id} enc={enc} />
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      )}

      {encounters.length === 0 && !isLoading && (
        <Text ta="center" c="dimmed" size="xs">
          Showing dashboard data — worklist updates automatically as encounters are opened.
        </Text>
      )}
    </Stack>
  );
}

function WorklistRow({ enc }: { enc: EncounterSummary }) {
  return (
    <Table.Tr>
      <Table.Td>
        <Anchor
          component={Link}
          to={`/patients/${enc.patient_nhid}`}
          size="sm"
          ff="monospace"
          fw={600}
        >
          {enc.patient_nhid}
        </Anchor>
      </Table.Td>
      <Table.Td>
        <Anchor component={Link} to={`/patients/${enc.patient_nhid}`} size="sm">
          {enc.patient_name}
        </Anchor>
      </Table.Td>
      <Table.Td>
        <Badge
          color={ENCOUNTER_TYPE_COLORS[enc.encounter_type] ?? "gray"}
          variant="light"
          size="sm"
        >
          {enc.encounter_type_display}
        </Badge>
      </Table.Td>
      <Table.Td>
        <Text size="sm">{enc.created_at_hospital?.name ?? "—"}</Text>
        {enc.is_cross_hospital && (
          <Badge color="yellow" size="xs" ml={4}>External</Badge>
        )}
      </Table.Td>
      <Table.Td>
        {enc.has_abnormal_labs && (
          <Badge color="red" size="xs">Abnormal Lab</Badge>
        )}
      </Table.Td>
      <Table.Td>
        <Text size="xs" c="dimmed">{dayjs(enc.created_at).fromNow()}</Text>
      </Table.Td>
      <Table.Td>
        <Group gap="xs">
          <Button
            component={Link}
            to={`/patients/${enc.patient_nhid}`}
            size="xs"
            variant="light"
          >
            Chart
          </Button>
          <Button
            component={Link}
            to={`/encounters/${enc.id}`}
            size="xs"
            variant="subtle"
          >
            Encounter
          </Button>
        </Group>
      </Table.Td>
    </Table.Tr>
  );
}
