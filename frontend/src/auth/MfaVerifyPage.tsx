import {
  Alert,
  Anchor,
  Box,
  Button,
  Center,
  Group,
  Paper,
  PinInput,
  Stack,
  Text,
  TextInput,
  ThemeIcon,
  Title,
} from "@mantine/core";
import { useForm } from "@mantine/form";
import { IconAlertCircle, IconDeviceMobile, IconKey, IconMail, IconShieldCheck } from "@tabler/icons-react";
import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { sendEmailOtp, verifyMfa } from "@/api/endpoints";
import { useAuth } from "./AuthProvider";

export function MfaVerifyPage() {
  const navigate         = useNavigate();
  const [params]         = useSearchParams();
  const { user }         = useAuth();
  const [code, setCode]  = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [useRecovery, setUseRecovery] = useState(false);
  const [sendingEmail, setSendingEmail] = useState(false);
  const [emailMsg, setEmailMsg] = useState<string | null>(null);

  const recoveryForm = useForm({
    initialValues: { recoveryCode: "" },
    validate: {
      recoveryCode: (v) =>
        v.trim().length >= 8 ? null : "Recovery codes are at least 8 characters",
    },
  });

  const next = params.get("next") || "/";

  // Clinical roles get the 8-hour trusted-device message; admins see a stricter note.
  const isClinical = user?.role === "doctor" || user?.role === "nurse" || user?.role === "lab_technician";
  const isAdmin    = user?.role === "super_admin" || user?.role === "hospital_admin";

  async function submit(codeToVerify: string) {
    if (!codeToVerify.trim()) return;
    setError(null);
    setLoading(true);
    try {
      await verifyMfa(codeToVerify.trim());
      navigate(next, { replace: true });
    } catch (err: unknown) {
      const e = err as { response?: { data?: { error?: string } } };
      setError(e?.response?.data?.error ?? "Invalid code. Please try again.");
      setCode("");
      recoveryForm.setFieldValue("recoveryCode", "");
    } finally {
      setLoading(false);
    }
  }

  async function handleSendEmailOtp() {
    setError(null);
    setEmailMsg(null);
    setSendingEmail(true);
    try {
      const res = await sendEmailOtp();
      setEmailMsg(res.data.detail || "Verification code sent to your email.");
    } catch (err: unknown) {
      const e = err as { response?: { data?: { error?: string } } };
      setError(e?.response?.data?.error ?? "Failed to send email verification code.");
    } finally {
      setSendingEmail(false);
    }
  }

  return (
    <Center h="100vh" bg="medsync.9">
      <Stack align="center" gap="xl" w={{ base: "90%", xs: 400 }}>
        <ThemeIcon size={56} radius="xl" color="medsync" variant="filled">
          <IconDeviceMobile size={32} />
        </ThemeIcon>

        <Paper p="xl" radius="md" w="100%" shadow="xl">
          <Title order={3} ta="center" mb={4}>Two-Factor Authentication</Title>

          {/* Role-specific hint */}
          {isClinical && (
            <Alert
              icon={<IconShieldCheck size={16} />}
              color="teal"
              variant="light"
              mb="md"
              radius="md"
            >
              <Text size="xs">
                After verifying, this device is trusted for <strong>8 hours</strong> — you
                won't need to enter a code again during your shift.
              </Text>
            </Alert>
          )}
          {isAdmin && (
            <Alert
              icon={<IconShieldCheck size={16} />}
              color="orange"
              variant="light"
              mb="md"
              radius="md"
            >
              <Text size="xs">
                Admin accounts require verification each session. Your device is trusted for
                <strong> 8 hours</strong> per sign-in.
              </Text>
            </Alert>
          )}

          <Text c="dimmed" size="sm" ta="center" mb="xl">
            {useRecovery
              ? "Enter one of your 10-character recovery codes."
              : "Enter the 6-digit code from your authenticator app or email."}
          </Text>

          {emailMsg && (
            <Alert color="teal" variant="light" mb="md" radius="md">
              <Text size="xs">{emailMsg}</Text>
            </Alert>
          )}

          {error && (
            <Alert icon={<IconAlertCircle />} color="red" mb="md" radius="md">
              {error}
            </Alert>
          )}

          {/* TOTP / Email OTP mode */}
          {!useRecovery && (
            <Stack gap="lg" align="center">
              <PinInput
                length={6}
                type="number"
                size="xl"
                value={code}
                onChange={setCode}
                onComplete={(val) => submit(val)}
                autoFocus
                aria-label="Verification code"
              />
              <Button
                fullWidth
                size="md"
                loading={loading}
                onClick={() => submit(code)}
                disabled={code.length < 6}
                color="medsync"
              >
                Verify
              </Button>

              <Button
                variant="subtle"
                color="medsync"
                size="xs"
                leftSection={<IconMail size={14} />}
                loading={sendingEmail}
                onClick={handleSendEmailOtp}
              >
                Email me a 6-digit code
              </Button>
            </Stack>
          )}

          {/* Recovery code mode */}
          {useRecovery && (
            <form onSubmit={recoveryForm.onSubmit((vals) => submit(vals.recoveryCode))}>
              <Stack gap="md">
                <TextInput
                  label="Recovery code"
                  placeholder="xxxxxxxxxx"
                  autoFocus
                  {...recoveryForm.getInputProps("recoveryCode")}
                />
                <Button type="submit" fullWidth size="md" loading={loading} color="medsync">
                  Verify recovery code
                </Button>
              </Stack>
            </form>
          )}

          {/* Toggle between OTP and recovery */}
          <Box mt="md" ta="center">
            {!useRecovery ? (
              <Anchor
                size="xs"
                c="dimmed"
                onClick={() => { setUseRecovery(true); setError(null); setCode(""); setEmailMsg(null); }}
              >
                <Group gap={4} justify="center" style={{ display: "inline-flex" }}>
                  <IconKey size={12} />
                  Use a recovery code instead
                </Group>
              </Anchor>
            ) : (
              <Anchor
                size="xs"
                c="dimmed"
                onClick={() => { setUseRecovery(false); setError(null); recoveryForm.reset(); setEmailMsg(null); }}
              >
                <Group gap={4} justify="center" style={{ display: "inline-flex" }}>
                  <IconDeviceMobile size={12} />
                  Use authenticator code instead
                </Group>
              </Anchor>
            )}
          </Box>
        </Paper>

        <Text size="xs" c="rgba(255,255,255,0.5)" ta="center">
          Lost access to your device?{" "}
          <Anchor size="xs" c="rgba(255,255,255,0.7)" onClick={() => setUseRecovery(true)}>
            Use a recovery code
          </Anchor>
          {" "}or contact your IT admin.
        </Text>
      </Stack>
    </Center>
  );
}
