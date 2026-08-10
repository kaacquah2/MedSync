/**
 * BedMapPage — visual ward bed grid for nurses.
 * Colour-coded by status: occupied=red, vacant=green, maintenance=orange, isolation=grey.
 * Click bed → popover with patient summary link.
 */

import {
  Badge,
  Box,
  Button,
  Card,
  Group,
  Popover,
  Select,
  SimpleGrid,
  Skeleton,
  Stack,
  Text,
  ThemeIcon,
  Title,
  Divider,
} from "@mantine/core";
import { IconBed, IconRefresh, IconUser } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { fetchWards } from "@/api/endpoints";
import type { Bed, Ward } from "@/types";

const BED_COLORS: Record<string, { bg: string; border: string; label: string; color: string }> = {
  occupied:    { bg: "var(--bg-red)",      border: "var(--accent-red)",   label: "Occupied",    color: "red" },
  available:   { bg: "var(--bg-green)",    border: "var(--accent-green)", label: "Vacant",      color: "green" },
  cleaning:    { bg: "var(--surface-1)",   border: "var(--border)",       label: "Isolation",   color: "gray" },
  maintenance: { bg: "var(--bg-amber)",    border: "var(--accent-amber)", label: "Maintenance", color: "orange" },
};

function BedCell({ bed }: { bed: Bed }) {
  const [opened, setOpened] = useState(false);

  let mappedStatus = bed.status;
  if (bed.status === "available") mappedStatus = "available";
  else if (bed.status === "occupied") mappedStatus = "occupied";
  else if (bed.status === "maintenance") mappedStatus = "maintenance";
  else mappedStatus = "cleaning";

  const style = BED_COLORS[mappedStatus] ?? BED_COLORS.available;

  return (
    <Popover opened={opened} onClose={() => setOpened(false)} position="top" withArrow shadow="md">
      <Popover.Target>
        <Box
          onClick={() => setOpened((o) => !o)}
          style={{
            cursor: "pointer",
            border: `1px solid ${style.border}`,
            borderLeft: `4px solid ${style.border}`,
            borderRadius: "var(--mantine-radius-md)",
            background: style.bg,
            padding: "12px 10px",
            textAlign: "center",
            minWidth: 90,
            transition: "transform 0.15s, box-shadow 0.15s",
            userSelect: "none",
          }}
          onMouseEnter={(e) => {
            (e.currentTarget as HTMLElement).style.transform = "translateY(-2px)";
            (e.currentTarget as HTMLElement).style.boxShadow = "var(--shadow-card)";
            setOpened(true);
          }}
          onMouseLeave={(e) => {
            (e.currentTarget as HTMLElement).style.transform = "";
            (e.currentTarget as HTMLElement).style.boxShadow = "";
            setOpened(false);
          }}
        >
          <Text size="xs" fw={700} mb={2} c="var(--text-primary)">{bed.label}</Text>
          {bed.patient_nhid ? (
            <Text size="xs" ff="monospace" c="var(--accent-red)" fw={700}>
              {bed.patient_nhid.substring(5)}
            </Text>
          ) : (
            <Text size="xs" c="var(--text-muted)">—</Text>
          )}
          <Badge size="10px" color={style.color} variant="light" mt={4}>
            {style.label}
          </Badge>
        </Box>
      </Popover.Target>

      <Popover.Dropdown style={{ pointerEvents: "auto" }}>
        <Stack gap={6} maw={220}>
          <Group gap="xs">
            <ThemeIcon size={24} radius="sm" color={style.color} variant="light">
              <IconBed size={14} />
            </ThemeIcon>
            <Text size="sm" fw={700}>{bed.label}</Text>
          </Group>
          <Badge color={style.color} variant="filled" size="sm">{style.label}</Badge>
          
          {bed.patient_nhid ? (
            <>
              <Divider my={2} />
              <Box>
                <Text size="10px" c="var(--text-muted)">PATIENT NHID</Text>
                <Text size="sm" fw={700} ff="monospace" c="var(--text-primary)">{bed.patient_nhid}</Text>
              </Box>
              <Button
                size="xs"
                variant="light"
                color="red"
                component={Link}
                to={`/patients/${bed.patient_nhid}`}
                leftSection={<IconUser size={12} />}
                onClick={() => setOpened(false)}
                mt={4}
              >
                Go to profile
              </Button>
            </>
          ) : (
            <Text size="xs" c="var(--text-muted)">Bed is currently empty and ready for admissions.</Text>
          )}
        </Stack>
      </Popover.Dropdown>
    </Popover>
  );
}

function WardMap({ ward }: { ward: Ward }) {
  const totalBeds    = ward.beds.length;
  const occupiedBeds = ward.beds.filter((b) => b.status === "occupied").length;
  const pct          = totalBeds > 0 ? Math.round((occupiedBeds / totalBeds) * 100) : 0;

  return (
    <Card withBorder radius="md" p="lg" mb="md" bg="var(--surface-2)">
      <Group justify="space-between" mb="md">
        <Group gap="xs">
          <ThemeIcon size={32} radius="md" color="medsync" variant="light">
            <IconBed size={18} />
          </ThemeIcon>
          <Box>
            <Text fw={700}>{ward.name}</Text>
            <Text size="xs" c="dimmed">
              {occupiedBeds}/{totalBeds} occupied · {pct}% occupancy
            </Text>
          </Box>
        </Group>
        <Group gap="xs">
          <Badge color="red"    variant="light" size="sm">Occupied: {occupiedBeds}</Badge>
          <Badge color="green"  variant="light" size="sm">Vacant: {ward.available_count}</Badge>
        </Group>
      </Group>

      {ward.beds.length === 0 ? (
        <Text c="dimmed" size="sm">No beds configured for this ward.</Text>
      ) : (
        <SimpleGrid
          cols={{ base: 3, sm: 5, md: 6, lg: 8 }}
          spacing="sm"
        >
          {ward.beds.map((bed) => (
            <BedCell key={bed.id} bed={bed} />
          ))}
        </SimpleGrid>
      )}
    </Card>
  );
}

export function BedMapPage() {
  const [wardFilter, setWardFilter] = useState<string | null>(null);

  const { data: wards, isLoading, refetch } = useQuery({
    queryKey: ["bed-map-wards"],
    queryFn:  () => fetchWards().then((r) => r.data),
    refetchInterval: 30_000,
  });

  const wardOptions = (wards ?? []).map((w) => ({ value: String(w.id), label: w.name }));
  const filteredWards = wardFilter
    ? (wards ?? []).filter((w) => String(w.id) === wardFilter)
    : (wards ?? []);

  const totalBeds     = (wards ?? []).reduce((s, w) => s + w.capacity, 0);
  const occupiedBeds  = (wards ?? []).reduce((s, w) => s + w.occupied_count, 0);

  return (
    <Stack gap="lg">
      <Group justify="space-between">
        <Group gap="xs">
          <ThemeIcon size={36} color="medsync" variant="light" radius="md">
            <IconBed size={20} />
          </ThemeIcon>
          <Box>
            <Title order={2} style={{ fontSize: "20px", fontWeight: 500 }}>Ward Bed Map</Title>
            <Text size="xs" c="dimmed">
              {occupiedBeds}/{totalBeds} beds occupied across {(wards ?? []).length} wards
            </Text>
          </Box>
        </Group>
        <Group gap="sm">
          <Select
            placeholder="All wards"
            data={wardOptions}
            value={wardFilter}
            onChange={setWardFilter}
            clearable
            size="sm"
            maw={200}
          />
          <Button leftSection={<IconRefresh size={16} />} variant="subtle" size="sm" onClick={() => refetch()} color="gray">
            Refresh
          </Button>
        </Group>
      </Group>

      {/* Legend */}
      <Group gap="md">
        {Object.entries(BED_COLORS).map(([status, style]) => (
          <Group key={status} gap={6}>
            <Box
              style={{
                width: 14,
                height: 14,
                borderRadius: 3,
                background: style.bg,
                border: `1.5px solid ${style.border}`,
              }}
            />
            <Text size="xs" c="dimmed">{style.label}</Text>
          </Group>
        ))}
      </Group>

      {isLoading ? (
        <Stack gap="md">
          {[1,2].map((i) => <Skeleton key={i} height={200} radius="md" />)}
        </Stack>
      ) : !filteredWards.length ? (
        <Box ta="center" py="xl">
          <Text c="dimmed">No wards found. Add wards in the Facilities section.</Text>
        </Box>
      ) : (
        filteredWards.map((ward) => (
          <WardMap key={ward.id} ward={ward} />
        ))
      )}
    </Stack>
  );
}
