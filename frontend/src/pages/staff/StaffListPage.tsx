import {
  ActionIcon,
  Badge,
  Button,
  Center,
  Group,
  Modal,
  Pagination,
  Select,
  Skeleton,
  Stack,
  Switch,
  Table,
  Text,
  TextInput,
  ThemeIcon,
  Title,
} from "@mantine/core";
import { useForm } from "@mantine/form";
import { useDisclosure } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import { IconCheck, IconEdit, IconUserPlus, IconUsers } from "@tabler/icons-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { createStaff, fetchHospitals, fetchStaff, setStaffActive, updateStaff } from "@/api/endpoints";
import { useAuth } from "@/auth/AuthProvider";
import type { Role, Staff } from "@/types";
import dayjs from "dayjs";

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

const ROLES: { value: Role; label: string }[] = [
  { value: "hospital_admin",  label: "Hospital Administrator" },
  { value: "doctor",          label: "Doctor" },
  { value: "nurse",           label: "Nurse" },
  { value: "lab_technician",  label: "Laboratory Technician" },
  { value: "receptionist",    label: "Receptionist" },
];

const ROLE_BADGE: Record<Role, string> = {
  super_admin:    "red",
  hospital_admin: "orange",
  doctor:         "blue",
  nurse:          "teal",
  lab_technician: "violet",
  receptionist:   "gray",
};

export function StaffListPage() {
  const { user } = useAuth();
  const qc       = useQueryClient();
  const [page, setPage] = useState(1);
  const [editTarget, setEditTarget] = useState<Staff | null>(null);
  const [createOpen, { open: openCreate, close: closeCreate }] = useDisclosure(false);
  const [editOpen,   { open: openEdit,   close: closeEdit   }] = useDisclosure(false);

  const { data: hospitalsData } = useQuery({
    queryKey: ["hospitals"],
    queryFn:  () => fetchHospitals().then((r) => r.data),
  });

  const { data, isLoading } = useQuery({
    queryKey: ["staff", page],
    queryFn:  () => fetchStaff({ page: String(page) }).then((r) => r.data),
  });

  const hospitalOptions = (hospitalsData?.results ?? []).map((h) => ({
    value: String(h.id),
    label: `${h.name} (${h.code})`,
  }));

  const rolesForUser: typeof ROLES =
    user?.role === "super_admin"
      ? [{ value: "super_admin", label: "System Administrator" }, ...ROLES]
      : ROLES;

  const createForm = useForm({
    initialValues: {
      username:    "",
      first_name:  "",
      last_name:   "",
      email:       "",
      role:        "doctor" as Role,
      hospital_id: user?.hospital ? String(user.hospital.id) : "",
      password:    "",
      phone:       "",
    },
    validate: {
      username:   (v) => (v.trim() ? null : "Required"),
      first_name: (v) => (v.trim() ? null : "Required"),
      last_name:  (v) => (v.trim() ? null : "Required"),
      email:      (v) => (v.includes("@") ? null : "Valid email required"),
      password:   (v) => (v.length >= 12 ? null : "Minimum 12 characters"),
    },
  });

  const editForm = useForm({
    initialValues: {
      first_name: "",
      last_name:  "",
      email:      "",
      role:       "doctor" as Role,
      phone:      "",
    },
  });

  async function handleCreate(values: typeof createForm.values) {
    try {
      await createStaff({ ...values, hospital_id: Number(values.hospital_id) || undefined });
      notifications.show({ color: "green", icon: <IconCheck />, message: "Staff member created." });
      qc.invalidateQueries({ queryKey: ["staff"] });
      closeCreate();
      createForm.reset();
    } catch (err) {
      notifications.show({ color: "red", message: formatApiError(err, "Failed to create staff.") });
    }
  }

  async function handleEdit(values: typeof editForm.values) {
    if (!editTarget) return;
    try {
      await updateStaff(editTarget.id, values);
      notifications.show({ color: "green", icon: <IconCheck />, message: "Staff member updated." });
      qc.invalidateQueries({ queryKey: ["staff"] });
      closeEdit();
    } catch (err) {
      notifications.show({ color: "red", message: formatApiError(err, "Failed to update.") });
    }
  }

  async function toggleActive(staff: Staff) {
    try {
      await setStaffActive(staff.id, !staff.is_active);
      notifications.show({ color: "green", message: `${staff.full_name} ${!staff.is_active ? "activated" : "deactivated"}.` });
      qc.invalidateQueries({ queryKey: ["staff"] });
    } catch (err) {
      notifications.show({ color: "red", message: formatApiError(err, "Failed to update status.") });
    }
  }

  function openEditModal(staff: Staff) {
    setEditTarget(staff);
    editForm.setValues({
      first_name: staff.first_name,
      last_name:  staff.last_name,
      email:      staff.email,
      role:       staff.role,
      phone:      staff.phone ?? "",
    });
    openEdit();
  }

  const totalPages = data ? Math.ceil(data.count / 30) : 1;

  return (
    <Stack gap="lg">
      <Group justify="space-between">
        <Group gap="xs">
          <ThemeIcon size={36} color="medsync" variant="light" radius="md">
            <IconUsers size={20} />
          </ThemeIcon>
          <Title order={2}>Staff Management</Title>
        </Group>
        <Button leftSection={<IconUserPlus size={16} />} onClick={openCreate}>Add Staff</Button>
      </Group>

      {isLoading ? (
        <Stack gap="xs">
          {[1, 2, 3, 4, 5].map((i) => <Skeleton key={i} height={52} radius="sm" />)}
        </Stack>
      ) : !data?.results.length ? (
        <Center py="xl">
          <Text c="dimmed" size="sm">No staff members found.</Text>
        </Center>
      ) : (
        <Table.ScrollContainer minWidth={800}>
          <Table striped highlightOnHover withTableBorder withColumnBorders>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Name</Table.Th>
                <Table.Th>Username</Table.Th>
                <Table.Th>Role</Table.Th>
                <Table.Th>Hospital</Table.Th>
                <Table.Th>MFA</Table.Th>
                <Table.Th>Status</Table.Th>
                <Table.Th>Joined</Table.Th>
                <Table.Th></Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {(data.results).map((s) => (
                <Table.Tr key={s.id} opacity={s.is_active ? 1 : 0.5}>
                  <Table.Td><Text fw={600}>{s.full_name}</Text></Table.Td>
                  <Table.Td><Text ff="monospace" size="sm">{s.username}</Text></Table.Td>
                  <Table.Td><Badge color={ROLE_BADGE[s.role]} variant="light" size="sm">{s.role_display}</Badge></Table.Td>
                  <Table.Td>{s.hospital?.name ?? "—"}</Table.Td>
                  <Table.Td>
                    <Badge color={s.mfa_enabled ? "green" : "gray"} size="sm" variant="dot">
                      {s.mfa_enabled ? "On" : "Off"}
                    </Badge>
                  </Table.Td>
                  <Table.Td>
                    <Badge color={s.is_active ? "green" : "red"} size="sm">
                      {s.is_active ? "Active" : "Inactive"}
                    </Badge>
                  </Table.Td>
                  <Table.Td>{dayjs(s.date_joined).format("DD MMM YYYY")}</Table.Td>
                  <Table.Td>
                    <Group gap="xs">
                      <ActionIcon variant="subtle" size="sm" onClick={() => openEditModal(s)}>
                        <IconEdit size={16} />
                      </ActionIcon>
                      {s.id !== user?.id && (
                        <Switch
                          size="xs"
                          checked={s.is_active}
                          onChange={() => toggleActive(s)}
                        />
                      )}
                    </Group>
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      )}

      {totalPages > 1 && <Pagination total={totalPages} value={page} onChange={setPage} />}

      {/* Create Staff Modal */}
      <Modal opened={createOpen} onClose={closeCreate} title="Add Staff Member" centered size="lg">
        <form onSubmit={createForm.onSubmit(handleCreate)}>
          <Stack>
            <Group grow>
              <TextInput label="First Name" required {...createForm.getInputProps("first_name")} />
              <TextInput label="Last Name" required {...createForm.getInputProps("last_name")} />
            </Group>
            <Group grow>
              <TextInput label="Username" required {...createForm.getInputProps("username")} />
              <TextInput label="Email" required {...createForm.getInputProps("email")} />
            </Group>
            <Group grow>
              <Select label="Role" data={rolesForUser} required {...createForm.getInputProps("role")} />
              {user?.role === "super_admin" && (
                <Select label="Hospital" data={hospitalOptions} clearable {...createForm.getInputProps("hospital_id")} />
              )}
            </Group>
            <TextInput label="Phone" {...createForm.getInputProps("phone")} />
            <TextInput label="Initial Password" type="password" description="Minimum 12 characters" required {...createForm.getInputProps("password")} />
            <Group justify="flex-end">
              <Button variant="subtle" onClick={closeCreate}>Cancel</Button>
              <Button type="submit">Create Staff</Button>
            </Group>
          </Stack>
        </form>
      </Modal>

      {/* Edit Staff Modal */}
      <Modal opened={editOpen} onClose={closeEdit} title={`Edit — ${editTarget?.full_name}`} centered>
        <form onSubmit={editForm.onSubmit(handleEdit)}>
          <Stack>
            <Group grow>
              <TextInput label="First Name" required {...editForm.getInputProps("first_name")} />
              <TextInput label="Last Name" required {...editForm.getInputProps("last_name")} />
            </Group>
            <TextInput label="Email" required {...editForm.getInputProps("email")} />
            <Select label="Role" data={rolesForUser} {...editForm.getInputProps("role")} />
            <TextInput label="Phone" {...editForm.getInputProps("phone")} />
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
