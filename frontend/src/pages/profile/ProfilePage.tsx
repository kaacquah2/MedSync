import {
  Alert,
  Avatar,
  Badge,
  Box,
  Button,
  Card,
  Code,
  CopyButton,
  Group,
  Modal,
  PasswordInput,
  PinInput,
  SimpleGrid,
  Stack,
  Text,
  TextInput,
  Textarea,
  ThemeIcon,
  Title,
} from "@mantine/core";
import { PageHeader } from "@/components/PageHeader";
import { useForm } from "@mantine/form";
import { useDisclosure } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import { IconCheck, IconCopy, IconDeviceMobile, IconKey, IconLogout, IconShield, IconUser } from "@tabler/icons-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  changePassword,
  disableMfa,
  fetchMfaStatus,
  getMfaSetup,
  confirmMfaSetup,
  signoutAll,
  updateMe,
} from "@/api/endpoints";
import { useAuth } from "@/auth/AuthProvider";

interface ApiErrorResponse {
  response?: {
    data?: {
      error?: string;
    };
  };
}

export function ProfilePage() {
  const { user, refresh } = useAuth();
  const qc       = useQueryClient();

  const [mfaSetupOpen, { open: openMfaSetup, close: closeMfaSetup }] = useDisclosure(false);
  const [mfaDisableOpen, { open: openDisable, close: closeDisable }] = useDisclosure(false);
  const [mfaCode, setMfaCode] = useState("");
  const [qrData, setQrData]   = useState<{ qr_code: string } | null>(null);
  const [recoveryCodes, setRecoveryCodes] = useState<string[] | null>(null);

  const { data: mfaStatus } = useQuery({
    queryKey: ["mfa-status"],
    queryFn:  () => fetchMfaStatus().then((r) => r.data),
  });

  const profileForm = useForm({
    initialValues: {
      first_name: user?.first_name ?? "",
      last_name:  user?.last_name  ?? "",
      email:      user?.email      ?? "",
      phone:      user?.phone      ?? "",
      bio:        user?.bio        ?? "",
    },
  });

  const pwForm = useForm({
    initialValues: { old_password: "", new_password: "", confirm: "" },
    validate: {
      new_password: (v) => (v.length >= 12 ? null : "Minimum 12 characters"),
      confirm:      (v, vals) => (v === vals.new_password ? null : "Passwords do not match"),
    },
  });

  async function saveProfile(values: typeof profileForm.values) {
    try {
      await updateMe(values);
      await refresh();
      notifications.show({ color: "green", icon: <IconCheck />, message: "Profile updated." });
    } catch {
      notifications.show({ color: "red", message: "Failed to update profile." });
    }
  }

  async function changePasswordSubmit(values: typeof pwForm.values) {
    try {
      await changePassword(values.old_password, values.new_password);
      notifications.show({ color: "green", icon: <IconCheck />, message: "Password changed." });
      pwForm.reset();
    } catch (err) {
      notifications.show({ color: "red", message: (err as ApiErrorResponse)?.response?.data?.error || "Failed." });
    }
  }

  async function openMfaSetupFlow() {
    const r = await getMfaSetup();
    setQrData(r.data);
    setMfaCode("");
    openMfaSetup();
  }

  async function confirmSetup() {
    try {
      const r = await confirmMfaSetup(mfaCode);
      setRecoveryCodes(r.data.recovery_codes);
      notifications.show({ color: "green", icon: <IconCheck />, message: "MFA enabled." });
      qc.invalidateQueries({ queryKey: ["mfa-status"] });
      closeMfaSetup();
    } catch (err) {
      notifications.show({ color: "red", message: (err as ApiErrorResponse)?.response?.data?.error || "Invalid code." });
    }
  }

  async function disableMfaSubmit() {
    try {
      await disableMfa(mfaCode);
      notifications.show({ color: "orange", message: "MFA disabled." });
      qc.invalidateQueries({ queryKey: ["mfa-status"] });
      closeDisable();
      setMfaCode("");
    } catch (err) {
      notifications.show({ color: "red", message: (err as ApiErrorResponse)?.response?.data?.error || "Invalid code." });
    }
  }

  async function handleSignoutAll() {
    await signoutAll();
    notifications.show({ color: "green", message: "All other sessions terminated." });
  }

  return (
    <Stack gap="lg">
      <PageHeader icon={<IconUser size={20} />} title="My Profile"
        subtitle={user?.hospital ? `${user?.role_display} · ${user.hospital.name}` : user?.role_display}
      />

      {/* Recovery codes (shown once after MFA setup) */}
      {recoveryCodes && (
        <Alert color="green" title="MFA Recovery Codes — Save These Now!" radius="md">
          <Text size="sm" mb="sm">These codes will NOT be shown again. Store them securely.</Text>
          <SimpleGrid cols={2} spacing="xs" mb="sm">
            {recoveryCodes.map((c) => <Code key={c} block ff="monospace" ta="center" p="xs">{c}</Code>)}
          </SimpleGrid>
          <CopyButton value={recoveryCodes.join("\n")}>
            {({ copied, copy }) => (
              <Button size="xs" variant="light" leftSection={copied ? <IconCheck size={14}/> : <IconCopy size={14}/>} onClick={copy}>
                {copied ? "Copied" : "Copy all"}
              </Button>
            )}
          </CopyButton>
        </Alert>
      )}

      <SimpleGrid cols={{ base: 1, md: 2 }} spacing="lg">
        {/* Profile info */}
        <Card withBorder radius="md" padding="lg">
          <Group mb="lg">
            <Avatar size={56} radius="xl" color="medsync">
              {user?.first_name?.[0] ?? user?.username?.[0]}
            </Avatar>
            <Box>
              <Text fw={700}>{user?.full_name}</Text>
              <Text size="sm" c="dimmed">@{user?.username}</Text>
              <Badge variant="light" mt={4}>{user?.role_display}</Badge>
            </Box>
          </Group>
          <form onSubmit={profileForm.onSubmit(saveProfile)}>
            <Stack gap="sm">
              <Group grow>
                <TextInput label="First Name" {...profileForm.getInputProps("first_name")} />
                <TextInput label="Last Name"  {...profileForm.getInputProps("last_name")} />
              </Group>
              <TextInput label="Email"  {...profileForm.getInputProps("email")} />
              <TextInput label="Phone"  {...profileForm.getInputProps("phone")} />
              <Textarea  label="Bio"    rows={2} {...profileForm.getInputProps("bio")} />
              <Button type="submit" mt="xs" leftSection={<IconUser size={16} />}>Save Profile</Button>
            </Stack>
          </form>
        </Card>

        {/* Security */}
        <Stack gap="md">
          {/* Change password */}
          <Card withBorder radius="md" padding="lg">
            <Group gap="xs" mb="md">
              <ThemeIcon size={28} color="medsync" variant="light" radius="md">
                <IconKey size={16} />
              </ThemeIcon>
              <Title order={5}>Change Password</Title>
            </Group>
            <form onSubmit={pwForm.onSubmit(changePasswordSubmit)}>
              <Stack gap="sm">
                <PasswordInput label="Current Password" {...pwForm.getInputProps("old_password")} />
                <PasswordInput label="New Password" description="Min. 12 characters" {...pwForm.getInputProps("new_password")} />
                <PasswordInput label="Confirm New Password" {...pwForm.getInputProps("confirm")} />
                <Button type="submit" leftSection={<IconShield size={16} />} variant="light">Update Password</Button>
              </Stack>
            </form>
          </Card>

          {/* MFA */}
          <Card withBorder radius="md" padding="lg">
            <Group justify="space-between" mb="md">
              <Group gap="xs">
                <ThemeIcon size={28} color="medsync" variant="light" radius="md">
                  <IconDeviceMobile size={16} />
                </ThemeIcon>
                <Title order={5}>Two-Factor Authentication</Title>
              </Group>
              <Badge color={mfaStatus?.mfa_enabled ? "green" : "gray"} size="lg">
                {mfaStatus?.mfa_enabled ? "Enabled" : "Disabled"}
              </Badge>
            </Group>
            <Text size="sm" c="dimmed" mb="md">
              MFA uses a TOTP authenticator app (Google Authenticator, Authy, etc.).
            </Text>
            <Group>
              {!mfaStatus?.mfa_enabled ? (
                <Button leftSection={<IconDeviceMobile size={16} />} onClick={openMfaSetupFlow} variant="light" color="green">
                  Enable MFA
                </Button>
              ) : (
                <Button leftSection={<IconDeviceMobile size={16} />} color="red" variant="light" onClick={openDisable}>
                  Disable MFA
                </Button>
              )}
            </Group>
          </Card>

          {/* Session security */}
          <Card withBorder radius="md" padding="lg">
            <Group gap="xs" mb="md">
              <ThemeIcon size={28} color="medsync" variant="light" radius="md">
                <IconShield size={16} />
              </ThemeIcon>
              <Title order={5}>Session Security</Title>
            </Group>
            <Button
              leftSection={<IconLogout size={16} />}
              color="red"
              variant="light"
              onClick={handleSignoutAll}
            >
              Sign Out All Other Sessions
            </Button>
            <Text size="xs" c="dimmed" mt="xs">
              Terminates all other active sessions and invalidates trusted-device cookies.
            </Text>
          </Card>
        </Stack>
      </SimpleGrid>

      {/* MFA Setup Modal */}
      <Modal opened={mfaSetupOpen} onClose={closeMfaSetup} title="Enable Two-Factor Authentication" centered>
        <Stack>
          {qrData && (
            <Box ta="center">
              <img src={qrData.qr_code} alt="MFA QR Code" style={{ width: 200, height: 200 }} />
            </Box>
          )}
          <Text size="sm" c="dimmed">Scan the QR code with your authenticator app, then enter the 6-digit code:</Text>
          <PinInput length={6} type="number" value={mfaCode} onChange={setMfaCode} onComplete={confirmSetup} autoFocus />
          <Group justify="flex-end">
            <Button variant="subtle" onClick={closeMfaSetup}>Cancel</Button>
            <Button onClick={confirmSetup} disabled={mfaCode.length < 6}>Verify & Enable</Button>
          </Group>
        </Stack>
      </Modal>

      {/* MFA Disable Modal */}
      <Modal opened={mfaDisableOpen} onClose={closeDisable} title="Disable MFA" centered>
        <Stack>
          <Alert color="red">Enter your current TOTP code to confirm you want to disable MFA.</Alert>
          <PinInput length={6} type="number" value={mfaCode} onChange={setMfaCode} onComplete={disableMfaSubmit} autoFocus />
          <Group justify="flex-end">
            <Button variant="subtle" onClick={closeDisable}>Cancel</Button>
            <Button color="red" onClick={disableMfaSubmit} disabled={mfaCode.length < 6}>Disable MFA</Button>
          </Group>
        </Stack>
      </Modal>
    </Stack>
  );
}
