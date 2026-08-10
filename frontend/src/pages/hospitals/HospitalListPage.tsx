import {
  Anchor,
  Badge,
  Box,
  Button,
  Card,
  Center,
  Group,
  Modal,
  SimpleGrid,
  Skeleton,
  Stack,
  Switch,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { useForm } from "@mantine/form";
import { useDisclosure } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import { IconBuilding, IconCheck, IconEdit, IconGlobe, IconMail, IconPhone, IconPlus } from "@tabler/icons-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { createHospital, fetchHospitals, updateHospital } from "@/api/endpoints";
import { useAuth } from "@/auth/AuthProvider";
import type { Hospital } from "@/types";

export function HospitalListPage() {
  const { user } = useAuth();
  const qc       = useQueryClient();
  const [editTarget, setEditTarget] = useState<Hospital | null>(null);
  const [createOpen, { open: openCreate, close: closeCreate }] = useDisclosure(false);
  const [editOpen,   { open: openEdit,   close: closeEdit   }] = useDisclosure(false);

  const { data, isLoading } = useQuery({
    queryKey: ["hospitals"],
    queryFn:  () => fetchHospitals().then((r) => r.data),
  });

  const isSystemAdmin = user?.role === "super_admin";

  const createForm = useForm({
    initialValues: { name: "", code: "", address: "", city: "", phone: "", email: "", website: "" },
    validate: {
      name: (v) => (v.trim() ? null : "Name is required"),
      code: (v) => (v.trim() ? null : "Code is required"),
    },
  });

  const editForm = useForm({
    initialValues: { name: "", code: "", address: "", city: "", phone: "", email: "", website: "", is_active: true },
  });

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

  async function handleCreate(values: typeof createForm.values) {
    try {
      await createHospital(values);
      notifications.show({ color: "green", icon: <IconCheck />, message: "Hospital created." });
      qc.invalidateQueries({ queryKey: ["hospitals"] });
      closeCreate(); createForm.reset();
    } catch (err) {
      notifications.show({ color: "red", message: formatApiError(err, "Failed to create hospital.") });
    }
  }

  async function handleEdit(values: typeof editForm.values) {
    if (!editTarget) return;
    try {
      await updateHospital(editTarget.id, values);
      notifications.show({ color: "green", icon: <IconCheck />, message: "Hospital updated." });
      qc.invalidateQueries({ queryKey: ["hospitals"] });
      closeEdit();
    } catch (err) {
      notifications.show({ color: "red", message: formatApiError(err, "Failed to update hospital.") });
    }
  }

  function openEditModal(h: Hospital) {
    setEditTarget(h);
    editForm.setValues({
      name: h.name, code: h.code, address: h.address ?? "", city: h.city ?? "",
      phone: h.phone ?? "", email: h.email ?? "", website: h.website ?? "", is_active: h.is_active,
    });
    openEdit();
  }

  return (
    <Stack gap="lg">
      <Group justify="space-between">
        <Title order={2}>Hospitals</Title>
        {isSystemAdmin && (
          <Button leftSection={<IconPlus size={16} />} onClick={openCreate}>Add Hospital</Button>
        )}
      </Group>

      {isLoading ? (
        <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }}>
          {[1, 2, 3].map((i) => <Skeleton key={i} height={160} radius="md" />)}
        </SimpleGrid>
      ) : !data?.results.length ? (
        <Center py="xl">
          <Text c="dimmed" size="sm">No hospitals configured yet.</Text>
        </Center>
      ) : (
        <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }}>
          {data.results.map((h) => (
            <Card key={h.id} withBorder radius="md" padding="lg">
              <Group justify="space-between" mb="sm">
                <Group>
                  <Badge
                    size="lg"
                    color="medsync"
                    variant="filled"
                    ff="monospace"
                    fw={800}
                    radius="md"
                    style={{ letterSpacing: "0.05em" }}
                  >
                    {h.code}
                  </Badge>
                  <Box>
                    <Text fw={700}>{h.name}</Text>
                    <Text size="xs" c="dimmed">{h.city}{h.city && h.country ? ", " : ""}{h.country}</Text>
                  </Box>
                </Group>
                <Badge color={h.is_active ? "green" : "red"} size="sm" variant="dot">
                  {h.is_active ? "Active" : "Inactive"}
                </Badge>
              </Group>
              <Stack gap={4} mt="xs">
                {h.phone && (
                  <Group gap="xs">
                    <IconPhone size={14} color="var(--mantine-color-dimmed)" />
                    <Text size="sm" c="dimmed">{h.phone}</Text>
                  </Group>
                )}
                {h.email && (
                  <Group gap="xs">
                    <IconMail size={14} color="var(--mantine-color-dimmed)" />
                    <Text size="sm" c="dimmed">{h.email}</Text>
                  </Group>
                )}
                {h.website && (
                  <Group gap="xs">
                    <IconGlobe size={14} color="var(--mantine-color-dimmed)" />
                    <Anchor href={h.website} size="sm" target="_blank">Website</Anchor>
                  </Group>
                )}
              </Stack>
              {isSystemAdmin && (
                <Button
                  leftSection={<IconEdit size={14} />}
                  size="xs"
                  variant="light"
                  mt="md"
                  onClick={() => openEditModal(h)}
                >
                  Edit
                </Button>
              )}
            </Card>
          ))}
        </SimpleGrid>
      )}

      <Modal opened={createOpen} onClose={closeCreate} title="Add Hospital" centered>
        <form onSubmit={createForm.onSubmit(handleCreate)}>
          <Stack>
            <TextInput label="Hospital Name" required {...createForm.getInputProps("name")} />
            <TextInput label="Short Code" description="e.g. UGMC, KATH" required {...createForm.getInputProps("code")} />
            <TextInput label="City" {...createForm.getInputProps("city")} />
            <TextInput label="Address" {...createForm.getInputProps("address")} />
            <TextInput label="Phone" {...createForm.getInputProps("phone")} />
            <TextInput label="Email" {...createForm.getInputProps("email")} />
            <TextInput label="Website" {...createForm.getInputProps("website")} />
            <Group justify="flex-end">
              <Button variant="subtle" onClick={closeCreate}>Cancel</Button>
              <Button type="submit" leftSection={<IconBuilding size={16} />}>Create Hospital</Button>
            </Group>
          </Stack>
        </form>
      </Modal>

      <Modal opened={editOpen} onClose={closeEdit} title={`Edit — ${editTarget?.name}`} centered>
        <form onSubmit={editForm.onSubmit(handleEdit)}>
          <Stack>
            <TextInput label="Hospital Name" required {...editForm.getInputProps("name")} />
            <TextInput label="Short Code" required {...editForm.getInputProps("code")} />
            <TextInput label="City" {...editForm.getInputProps("city")} />
            <TextInput label="Address" {...editForm.getInputProps("address")} />
            <TextInput label="Phone" {...editForm.getInputProps("phone")} />
            <TextInput label="Email" {...editForm.getInputProps("email")} />
            <TextInput label="Website" {...editForm.getInputProps("website")} />
            <Switch label="Active" {...editForm.getInputProps("is_active", { type: "checkbox" })} />
            <Group justify="flex-end">
              <Button variant="subtle" onClick={closeEdit}>Cancel</Button>
              <Button type="submit">Save Changes</Button>
            </Group>
          </Stack>
        </form>
      </Modal>
    </Stack>
  );
}
