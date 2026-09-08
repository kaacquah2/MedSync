import {
  Badge,
  Box,
  Button,
  Card,
  Group,
  Modal,
  Pagination,
  PasswordInput,
  Select,
  Skeleton,
  Stack,
  Table,
  Text,
  TextInput,
  ThemeIcon,
  Title,
} from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import { useForm } from "@mantine/form";
import { notifications } from "@mantine/notifications";
import {
  IconCheck,
  IconKey,
  IconLock,
  IconLockOpen,
  IconPlus,
  IconSearch,
  IconUserOff,
  IconUsers,
} from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import dayjs from "dayjs";
import { useState } from "react";
import {
  createStaff,
  fetchHospitals,
  fetchStaff,
  resetStaffPassword,
  setStaffActive,
  updateStaff,
} from "@/api/endpoints";
import { useAuth } from "@/auth/AuthProvider";
import type { Role, Staff } from "@/types";
import { ROLE_COLORS } from "@/constants/roles";

const BASE_ROLES = [
  { value: "doctor",         label: "Doctor" },
  { value: "nurse",          label: "Nurse" },
  { value: "lab_technician", label: "Lab Technician" },
  { value: "receptionist",   label: "Receptionist" },
  { value: "hospital_admin", label: "Hospital Admin" },
];

const ALL_ROLES = [
  ...BASE_ROLES,
  { value: "super_admin", label: "Super Admin" },
];

interface StaffUserTableProps {
  /** "hospital" = hospital_admin view (own hospital only); "all" = super_admin cross-hospital view. */
  scope: "hospital" | "all";
}

export function StaffUserTable({ scope }: StaffUserTableProps) {
  const { user } = useAuth();
  const qc = useQueryClient();
  const [page, setPage]           = useState(1);
  const [search, setSearch]       = useState("");
  const [roleFilter, setRoleFilter] = useState<string | null>(null);
  const [editStaff, setEditStaff] = useState<Staff | null>(null);
  const [resetTarget, setResetTarget] = useState<Staff | null>(null);

  const [editOpen,   { open: openEdit,   close: closeEdit   }] = useDisclosure(false);
  const [inviteOpen, { open: openInvite, close: closeInvite }] = useDisclosure(false);
  const [resetOpen,  { open: openReset,  close: closeReset  }] = useDisclosure(false);

  const queryKey  = scope === "hospital" ? "staff-hospital" : "staff-all";
  const roleOptions = scope === "all" ? ALL_ROLES : BASE_ROLES;

  const { data, isLoading } = useQuery({
    queryKey: [queryKey, page, search, roleFilter],
    queryFn: () =>
      fetchStaff({
        page: String(page),
        ...(search ? { q: search } : {}),
        ...(scope === "all" && roleFilter ? { role: roleFilter } : {}),
      }).then((r) => r.data),
    staleTime: 30_000,
  });

  const { data: hospitalsData } = useQuery({
    queryKey: ["hospitals"],
    queryFn: () => fetchHospitals().then((r) => r.data),
    staleTime: 5 * 60_000,
    enabled: scope === "all",
  });
  const hospitalOptions =
    hospitalsData?.results?.map((h) => ({ value: String(h.id), label: h.name })) ?? [];

  // ── Activate / deactivate ─────────────────────────────────────────────────
  const activateMutation = useMutation({
    mutationFn: ({ id, active }: { id: number; active: boolean }) =>
      setStaffActive(id, active),
    onSuccess: (_, vars) => {
      notifications.show({
        color: "green",
        icon: <IconCheck />,
        message: vars.active ? "User activated." : "User deactivated.",
      });
      qc.invalidateQueries({ queryKey: [queryKey] });
    },
    onError: () => notifications.show({ color: "red", message: "Action failed." }),
  });

  // ── Edit role ─────────────────────────────────────────────────────────────
  const editForm = useForm({ initialValues: { role: "" as Role } });

  const editMutation = useMutation({
    mutationFn: ({ id, role }: { id: number; role: Role }) => updateStaff(id, { role }),
    onSuccess: () => {
      notifications.show({ color: "green", icon: <IconCheck />, message: "Role updated." });
      qc.invalidateQueries({ queryKey: [queryKey] });
      closeEdit();
    },
    onError: () => notifications.show({ color: "red", message: "Failed to update role." }),
  });

  function openEditModal(s: Staff) {
    setEditStaff(s);
    editForm.setValues({ role: s.role });
    openEdit();
  }

  // ── Create staff ──────────────────────────────────────────────────────────
  const createForm = useForm({
    initialValues: {
      username:    "",
      first_name:  "",
      last_name:   "",
      email:       "",
      role:        "" as Role,
      hospital_id: "",
      password:    "",
    },
    validate: {
      username:   (v) => v.trim() ? null : "Username is required",
      first_name: (v) => v.trim() ? null : "First name is required",
      last_name:  (v) => v.trim() ? null : "Last name is required",
      email:      (v) =>
        /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v) ? null : "Valid email required",
      role:     (v) => v ? null : "Role is required",
      password: (v) =>
        v.length >= 12 ? null : "Password must be at least 12 characters",
    },
  });

  const createMutation = useMutation({
    mutationFn: (values: typeof createForm.values) => {
      const payload: Record<string, unknown> = { ...values };
      if (scope === "all" && payload.hospital_id) {
        payload.hospital_id = Number(payload.hospital_id);
      } else {
        delete payload.hospital_id;
      }
      return createStaff(payload);
    },
    onSuccess: () => {
      notifications.show({
        color: "green",
        icon: <IconCheck />,
        message: "Staff member created.",
      });
      qc.invalidateQueries({ queryKey: [queryKey] });
      createForm.reset();
      closeInvite();
    },
    onError: (err: unknown) => {
      const msg =
        (err as { response?: { data?: { error?: string } } })?.response?.data?.error ??
        "Failed to create staff member.";
      notifications.show({ color: "red", message: msg });
    },
  });

  // ── Reset password ────────────────────────────────────────────────────────
  const resetForm = useForm({
    initialValues: { password: "" },
    validate: {
      password: (v) =>
        v.length >= 12 ? null : "Password must be at least 12 characters",
    },
  });

  const resetMutation = useMutation({
    mutationFn: ({ id, password }: { id: number; password: string }) =>
      resetStaffPassword(id, password),
    onSuccess: () => {
      notifications.show({
        color: "green",
        icon: <IconCheck />,
        message: "Password reset successfully.",
      });
      resetForm.reset();
      closeReset();
    },
    onError: (err: unknown) => {
      const msg =
        (err as { response?: { data?: { error?: string } } })?.response?.data?.error ??
        "Failed to reset password.";
      notifications.show({ color: "red", message: msg });
    },
  });

  function openResetModal(s: Staff) {
    setResetTarget(s);
    resetForm.reset();
    openReset();
  }

  const staff = data?.results ?? [];
  const totalPages = data ? Math.ceil(data.count / 20) : 1;

  const title    = scope === "hospital" ? "Hospital Users" : "User Management";
  const subtitle =
    scope === "hospital"
      ? `${user?.hospital?.name ?? ""} · ${data?.count ?? "—"} staff members`
      : `All staff across all hospitals · ${data?.count ?? "—"} total users`;

  return (
    <Stack gap="lg">
      <Group justify="space-between">
        <Group gap="xs">
          <ThemeIcon size={36} color="medsync" variant="light" radius="md">
            <IconUsers size={20} />
          </ThemeIcon>
          <Box>
            <Title order={2}>{title}</Title>
            <Text size="xs" c="dimmed">{subtitle}</Text>
          </Box>
        </Group>
        <Button
          leftSection={<IconPlus size={16} />}
          onClick={() => { createForm.reset(); openInvite(); }}
        >
          Add Staff Member
        </Button>
      </Group>

      {/* Filters */}
      <Group gap="sm" wrap="wrap">
        <TextInput
          placeholder="Search by name or username…"
          leftSection={<IconSearch size={16} />}
          value={search}
          onChange={(e) => { setSearch(e.target.value); setPage(1); }}
          maw={300}
          size="sm"
        />
        {scope === "all" && (
          <Select
            placeholder="Filter by role"
            data={roleOptions}
            value={roleFilter}
            onChange={(v) => { setRoleFilter(v); setPage(1); }}
            clearable
            maw={200}
            size="sm"
          />
        )}
        {(search || roleFilter) && (
          <Button
            variant="subtle"
            size="sm"
            onClick={() => { setSearch(""); setRoleFilter(null); setPage(1); }}
          >
            Clear
          </Button>
        )}
      </Group>

      {isLoading ? (
        <Stack gap="xs">
          {[1, 2, 3, 4, 5].map((i) => <Skeleton key={i} height={52} radius="sm" />)}
        </Stack>
      ) : !staff.length ? (
        <Box ta="center" py="xl"><Text c="dimmed">No staff found.</Text></Box>
      ) : (
        <Card withBorder radius="md" p={0}>
          <Table.ScrollContainer minWidth={scope === "all" ? 900 : 800}>
            <Table striped highlightOnHover withTableBorder withColumnBorders>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Name</Table.Th>
                  {scope === "all" ? (
                    <>
                      <Table.Th>Username</Table.Th>
                      <Table.Th>Role</Table.Th>
                      <Table.Th>Hospital</Table.Th>
                    </>
                  ) : (
                    <>
                      <Table.Th>Role</Table.Th>
                      <Table.Th>Email</Table.Th>
                    </>
                  )}
                  <Table.Th>Joined</Table.Th>
                  <Table.Th>MFA</Table.Th>
                  <Table.Th>Status</Table.Th>
                  <Table.Th>Actions</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {staff.map((s) => (
                  <Table.Tr key={s.id}>
                    <Table.Td>
                      <Text size="sm" fw={600}>{s.full_name}</Text>
                      <Text size="xs" c="dimmed">
                        {scope === "all" ? s.email : s.username}
                      </Text>
                    </Table.Td>
                    {scope === "all" ? (
                      <>
                        <Table.Td>
                          <Text size="sm" ff="monospace">{s.username}</Text>
                        </Table.Td>
                        <Table.Td>
                          <Badge color={ROLE_COLORS[s.role] ?? "gray"} variant="light" size="sm">
                            {s.role_display}
                          </Badge>
                        </Table.Td>
                        <Table.Td>
                          <Text size="sm">{s.hospital?.name ?? "—"}</Text>
                        </Table.Td>
                      </>
                    ) : (
                      <>
                        <Table.Td>
                          <Badge color={ROLE_COLORS[s.role] ?? "gray"} variant="light" size="sm">
                            {s.role_display}
                          </Badge>
                        </Table.Td>
                        <Table.Td><Text size="xs">{s.email}</Text></Table.Td>
                      </>
                    )}
                    <Table.Td>
                      <Text size="xs" c="dimmed">
                        {dayjs(s.date_joined).format("DD MMM YYYY")}
                      </Text>
                    </Table.Td>
                    <Table.Td>
                      <Badge
                        color={s.mfa_enabled ? "green" : "red"}
                        size="xs"
                        variant="light"
                      >
                        {s.mfa_enabled
                          ? (scope === "all" ? "On" : "Enabled")
                          : (scope === "all" ? "Off" : "Disabled")}
                      </Badge>
                    </Table.Td>
                    <Table.Td>
                      <Badge
                        color={s.is_active ? "green" : "red"}
                        variant="light"
                        size="sm"
                      >
                        {s.is_active ? "Active" : "Inactive"}
                      </Badge>
                    </Table.Td>
                    <Table.Td>
                      <Group gap={4} wrap="nowrap">
                        <Button
                          size="xs"
                          variant="light"
                          onClick={() => openEditModal(s)}
                        >
                          Edit role
                        </Button>
                        <Button
                          size="xs"
                          variant="subtle"
                          color="orange"
                          leftSection={<IconKey size={12} />}
                          onClick={() => openResetModal(s)}
                        >
                          Reset pwd
                        </Button>
                        <Button
                          size="xs"
                          variant="subtle"
                          color={s.is_active ? "red" : "green"}
                          leftSection={
                            s.is_active
                              ? <IconUserOff size={12} />
                              : <IconLockOpen size={12} />
                          }
                          loading={activateMutation.isPending}
                          onClick={() =>
                            activateMutation.mutate({ id: s.id, active: !s.is_active })
                          }
                        >
                          {s.is_active ? "Deactivate" : "Activate"}
                        </Button>
                      </Group>
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        </Card>
      )}

      {totalPages > 1 && (
        <Group justify="center">
          <Pagination total={totalPages} value={page} onChange={setPage} />
        </Group>
      )}

      {/* Edit role modal */}
      <Modal
        opened={editOpen}
        onClose={closeEdit}
        title={`Edit Role — ${editStaff?.full_name}`}
        centered
      >
        <form
          onSubmit={editForm.onSubmit((v) =>
            editMutation.mutate({ id: editStaff!.id, role: v.role as Role })
          )}
        >
          <Stack>
            <Select
              label="Role"
              data={roleOptions}
              required
              {...editForm.getInputProps("role")}
            />
            <Group justify="flex-end">
              <Button variant="subtle" onClick={closeEdit}>Cancel</Button>
              <Button
                type="submit"
                loading={editMutation.isPending}
                leftSection={<IconCheck size={16} />}
              >
                {scope === "all" ? "Save Role" : "Save"}
              </Button>
            </Group>
          </Stack>
        </form>
      </Modal>

      {/* Add Staff Member modal */}
      <Modal opened={inviteOpen} onClose={closeInvite} title="Add Staff Member" centered>
        <form onSubmit={createForm.onSubmit((v) => createMutation.mutate(v))}>
          <Stack>
            <Group grow>
              <TextInput
                label="First name"
                placeholder={scope === "all" ? "Kofi" : "Kwame"}
                required
                {...createForm.getInputProps("first_name")}
              />
              <TextInput
                label="Last name"
                placeholder={scope === "all" ? "Mensah" : "Asante"}
                required
                {...createForm.getInputProps("last_name")}
              />
            </Group>
            <TextInput
              label="Username"
              placeholder={scope === "all" ? "kmensah" : "kasante"}
              required
              {...createForm.getInputProps("username")}
            />
            <TextInput
              label="Email address"
              placeholder={
                scope === "all" ? "kmensah@kath.edu.gh" : "kasante@ugmc.edu.gh"
              }
              type="email"
              required
              {...createForm.getInputProps("email")}
            />
            <Select
              label="Role"
              data={roleOptions}
              placeholder="Select a role"
              required
              {...createForm.getInputProps("role")}
            />
            {scope === "all" && (
              <Select
                label="Hospital"
                data={hospitalOptions}
                placeholder="Select a hospital"
                searchable
                clearable
                {...createForm.getInputProps("hospital_id")}
              />
            )}
            <PasswordInput
              label="Initial password"
              placeholder="Minimum 12 characters"
              required
              description="The staff member should change this on first login."
              {...createForm.getInputProps("password")}
            />
            <Group justify="flex-end">
              <Button variant="subtle" onClick={closeInvite}>Cancel</Button>
              <Button
                type="submit"
                loading={createMutation.isPending}
                leftSection={<IconCheck size={16} />}
              >
                Create Staff Member
              </Button>
            </Group>
          </Stack>
        </form>
      </Modal>

      {/* Reset Password modal */}
      <Modal
        opened={resetOpen}
        onClose={closeReset}
        title={`Reset Password — ${resetTarget?.full_name}`}
        centered
      >
        <form
          onSubmit={resetForm.onSubmit((v) =>
            resetMutation.mutate({ id: resetTarget!.id, password: v.password })
          )}
        >
          <Stack>
            <Text size="sm" c="dimmed">
              {scope === "all" ? (
                <>
                  Set a temporary password for{" "}
                  <strong>{resetTarget?.username}</strong> at{" "}
                  <strong>{resetTarget?.hospital?.name ?? "unknown hospital"}</strong>.
                  They should change it after their next login.
                </>
              ) : (
                <>
                  Set a temporary password for{" "}
                  <strong>{resetTarget?.username}</strong>.
                  They should change it after their next login.
                </>
              )}
            </Text>
            <PasswordInput
              label="New temporary password"
              placeholder="Minimum 12 characters"
              required
              {...resetForm.getInputProps("password")}
            />
            <Group justify="flex-end">
              <Button variant="subtle" onClick={closeReset}>Cancel</Button>
              <Button
                type="submit"
                color="orange"
                loading={resetMutation.isPending}
                leftSection={
                  scope === "all" ? <IconLock size={16} /> : <IconKey size={16} />
                }
              >
                Reset Password
              </Button>
            </Group>
          </Stack>
        </form>
      </Modal>
    </Stack>
  );
}
