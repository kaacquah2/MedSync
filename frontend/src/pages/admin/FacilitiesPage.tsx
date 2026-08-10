import {
  Accordion,
  Badge,
  Box,
  Button,
  Card,
  Grid,
  Group,
  Progress,
  SimpleGrid,
  Skeleton,
  Stack,
  Text,
  ThemeIcon,
  Title,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconBuilding, IconBed } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchWards, updateBedStatus } from "@/api/endpoints";
import type { Bed, Ward } from "@/types";

const BED_STATUS_COLORS: Record<Bed["status"], string> = {
  available:   "green",
  occupied:    "red",
  cleaning:    "yellow",
  maintenance: "gray",
};

function BedTile({ bed, canEdit, onStatusChange }: {
  bed: Bed;
  canEdit: boolean;
  onStatusChange: (id: number, status: string) => void;
}) {
  const color = BED_STATUS_COLORS[bed.status] ?? "gray";
  return (
    <Card
      withBorder
      p="xs"
      radius="sm"
      style={{ borderLeftWidth: 3, borderLeftColor: `var(--mantine-color-${color}-6)` }}
    >
      <Text fw={700} size="sm">{bed.label}</Text>
      <Badge color={color} size="xs" variant="dot" mb={4}>
        {bed.status_display}
      </Badge>
      {bed.patient_nhid && (
        <Text size="xs" c="dimmed" ff="monospace">{bed.patient_nhid}</Text>
      )}
      {canEdit && bed.status !== "available" && (
        <Button
          size="xs"
          variant="subtle"
          color="green"
          mt={4}
          fullWidth
          onClick={() => onStatusChange(bed.id, "available")}
        >
          Mark Available
        </Button>
      )}
    </Card>
  );
}

function WardCard({ ward, canEdit, onBedStatusChange }: {
  ward: Ward;
  canEdit: boolean;
  onBedStatusChange: (id: number, status: string) => void;
}) {
  const occupancyPct = ward.capacity > 0
    ? Math.round((ward.occupied_count / ward.capacity) * 100)
    : 0;
  const occupancyColor = occupancyPct >= 90 ? "red" : occupancyPct >= 70 ? "orange" : "green";

  return (
    <Card withBorder radius="lg" p="lg">
      <Group justify="space-between" mb="sm">
        <Group gap="sm">
          <ThemeIcon size={36} color="medsync" variant="light" radius="md">
            <IconBuilding size={20} />
          </ThemeIcon>
          <Box>
            <Text fw={700}>{ward.name}</Text>
            <Text size="xs" c="dimmed" ff="monospace">{ward.code}</Text>
          </Box>
        </Group>
        <Badge color={occupancyColor} variant="light">
          {ward.occupied_count}/{ward.capacity} beds
        </Badge>
      </Group>

      <Progress
        value={occupancyPct}
        color={occupancyColor}
        size="sm"
        mb="md"
        radius="xl"
      />

      <Text size="xs" c="dimmed" mb="sm">
        {ward.available_count} available · {ward.occupied_count} occupied
      </Text>

      {ward.beds.length > 0 ? (
        <Accordion variant="separated">
          <Accordion.Item value="beds">
            <Accordion.Control>
              <Text size="sm" fw={500}>
                View {ward.beds.length} Bed{ward.beds.length !== 1 ? "s" : ""}
              </Text>
            </Accordion.Control>
            <Accordion.Panel>
              <SimpleGrid cols={{ base: 2, sm: 3 }} spacing="xs">
                {ward.beds.map((bed) => (
                  <BedTile
                    key={bed.id}
                    bed={bed}
                    canEdit={canEdit}
                    onStatusChange={onBedStatusChange}
                  />
                ))}
              </SimpleGrid>
            </Accordion.Panel>
          </Accordion.Item>
        </Accordion>
      ) : (
        <Text size="xs" c="dimmed" ta="center" py="sm">No beds configured.</Text>
      )}
    </Card>
  );
}

export function FacilitiesPage() {
  const qc = useQueryClient();

  const { data: wards, isLoading } = useQuery({
    queryKey: ["wards"],
    queryFn: () => fetchWards().then((r) => r.data),
  });

  const bedMutation = useMutation({
    mutationFn: ({ id, status }: { id: number; status: string }) =>
      updateBedStatus(id, status),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["wards"] });
      notifications.show({ color: "green", message: "Bed status updated." });
    },
    onError: () => notifications.show({ color: "red", message: "Update failed." }),
  });

  const totalBeds     = wards?.reduce((sum, w) => sum + w.capacity, 0) ?? 0;
  const occupiedBeds  = wards?.reduce((sum, w) => sum + w.occupied_count, 0) ?? 0;
  const availableBeds = wards?.reduce((sum, w) => sum + w.available_count, 0) ?? 0;

  return (
    <Stack gap="lg">
      <Group justify="space-between">
        <Group gap="xs">
          <ThemeIcon size={36} color="medsync" variant="light" radius="md">
            <IconBed size={20} />
          </ThemeIcon>
          <Title order={2}>Wards & Beds</Title>
        </Group>
      </Group>

      {/* Summary KPIs */}
      <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="md">
        {[
          { label: "Total Beds", value: totalBeds, color: "blue" },
          { label: "Occupied",   value: occupiedBeds, color: "red" },
          { label: "Available",  value: availableBeds, color: "green" },
        ].map((kpi) => (
          <Card key={kpi.label} withBorder p="md" radius="md">
            <Text size="xs" c="dimmed" tt="uppercase" fw={500} mb={4}>{kpi.label}</Text>
            <Text size="xl" fw={700} c={kpi.color}>{kpi.value}</Text>
          </Card>
        ))}
      </SimpleGrid>

      {isLoading ? (
        <Grid>
          {[1, 2, 3].map((i) => (
            <Grid.Col key={i} span={{ base: 12, md: 6 }}>
              <Skeleton height={200} radius="lg" />
            </Grid.Col>
          ))}
        </Grid>
      ) : !wards?.length ? (
        <Box ta="center" py="xl">
          <Text c="dimmed">No wards configured for this hospital.</Text>
        </Box>
      ) : (
        <Grid>
          {wards.map((ward) => (
            <Grid.Col key={ward.id} span={{ base: 12, md: 6 }}>
              <WardCard
                ward={ward}
                canEdit
                onBedStatusChange={(id, status) => bedMutation.mutate({ id, status })}
              />
            </Grid.Col>
          ))}
        </Grid>
      )}
    </Stack>
  );
}
