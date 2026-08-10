import {
  Alert,
  Box,
  Button,
  Center,
  Code,
  CopyButton,
  Divider,
  Group,
  Image,
  List,
  Paper,
  PinInput,
  SimpleGrid,
  Stack,
  Text,
  ThemeIcon,
  Title,
} from "@mantine/core";
import {
  IconAlertCircle,
  IconCheck,
  IconCopy,
  IconShield,
} from "@tabler/icons-react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { confirmMfaSetup, getMfaSetup } from "@/api/endpoints";

interface ApiErrorResponse {
  response?: {
    data?: {
      error?: string;
    };
  };
}

export function MfaSetupPage() {
  const navigate = useNavigate();
  const [qr, setQr]             = useState<string | null>(null);
  const [uri, setUri]             = useState("");
  const [code, setCode]           = useState("");
  const [error, setError]         = useState<string | null>(null);
  const [loading, setLoading]     = useState(false);
  const [recoveryCodes, setRecoveryCodes] = useState<string[] | null>(null);
  const [step, setStep] = useState<"scan" | "confirm" | "codes">("scan");

  useEffect(() => {
    getMfaSetup().then((r) => {
      setQr(r.data.qr_code);
      setUri(r.data.uri);
    });
  }, []);

  async function handleConfirm() {
    if (code.length < 6) return;
    setError(null);
    setLoading(true);
    try {
      const res = await confirmMfaSetup(code);
      setRecoveryCodes(res.data.recovery_codes);
      setStep("codes");
    } catch (err: unknown) {
      setError((err as ApiErrorResponse)?.response?.data?.error || "Invalid code.");
      setCode("");
    } finally {
      setLoading(false);
    }
  }

  if (step === "codes" && recoveryCodes) {
    return (
      <Center h="100vh" bg="medsync.9">
        <Stack align="center" gap="xl" w={{ base: "90%", sm: 520 }}>
          <ThemeIcon size={56} radius="xl" color="clinical" variant="filled">
            <IconCheck size={32} />
          </ThemeIcon>

          <Paper p="xl" radius="md" w="100%" shadow="xl">
            <Title order={3} ta="center" mb="xs" c="clinical.5">MFA Enabled</Title>
            <Text c="dimmed" size="sm" ta="center" mb="xl">
              Save these recovery codes in a secure location. Each code can only be used once.
            </Text>

            <Alert color="warn" mb="xl" radius="md">
              <Text size="sm" fw={700}>These codes will NOT be shown again.</Text>
              <Text size="sm">Store them securely — you will need them if you lose access to your authenticator app.</Text>
            </Alert>

            <SimpleGrid cols={2} spacing="xs" mb="xl">
              {recoveryCodes.map((c) => (
                <Code key={c} block ff="monospace" ta="center" p="xs">
                  {c}
                </Code>
              ))}
            </SimpleGrid>

            <CopyButton value={recoveryCodes.join("\n")}>
              {({ copied, copy }) => (
                <Button
                  fullWidth
                  leftSection={copied ? <IconCheck size={16} /> : <IconCopy size={16} />}
                  color={copied ? "clinical" : "medsync"}
                  onClick={copy}
                  mb="md"
                  variant="light"
                >
                  {copied ? "Copied!" : "Copy all codes"}
                </Button>
              )}
            </CopyButton>

            <Button
              fullWidth
              size="md"
              onClick={() => navigate("/", { replace: true })}
              color="medsync"
            >
              Continue to Dashboard
            </Button>
          </Paper>
        </Stack>
      </Center>
    );
  }

  return (
    <Center h="100vh" bg="medsync.9">
      <Stack align="center" gap="xl" w={{ base: "90%", sm: 480 }}>
        <Group>
          <ThemeIcon size={56} radius="xl" color="medsync" variant="filled">
            <IconShield size={32} />
          </ThemeIcon>
          <Box>
            <Title order={2} c="white">Set Up MFA</Title>
            <Text c="medsync.2" size="sm">Protect your account with TOTP</Text>
          </Box>
        </Group>

        <Paper p="xl" radius="md" w="100%" shadow="xl">
          <Stack>
            <List spacing="sm" size="sm">
              <List.Item>Download <Text component="span" fw={700}>Google Authenticator</Text>, <Text component="span" fw={700}>Authy</Text>, or any TOTP app.</List.Item>
              <List.Item>Scan the QR code below with your authenticator app.</List.Item>
              <List.Item>Enter the 6-digit code to confirm.</List.Item>
            </List>

            <Divider />

            {qr ? (
              <Center>
                <Image src={qr} alt="MFA QR Code" w={200} h={200} radius="md" />
              </Center>
            ) : (
              <Center h={200}><Text c="dimmed">Loading QR code…</Text></Center>
            )}

            <Text size="xs" c="dimmed" ta="center">
              Can&apos;t scan? Enter this URI in your app manually.
            </Text>

            {uri && (
              <Code block ff="monospace" ta="center" p="xs" style={{ wordBreak: "break-all" }}>
                {uri}
              </Code>
            )}

            {error && (
              <Alert icon={<IconAlertCircle />} color="red" radius="md">
                {error}
              </Alert>
            )}

            <Stack align="center" gap="sm">
              <PinInput
                length={6}
                type="number"
                size="lg"
                value={code}
                onChange={setCode}
                onComplete={handleConfirm}
                autoFocus={!!qr}
              />
              <Button
                fullWidth
                size="md"
                loading={loading}
                onClick={handleConfirm}
                disabled={code.length < 6}
                color="medsync"
              >
                Enable MFA
              </Button>
            </Stack>
          </Stack>
        </Paper>
      </Stack>
    </Center>
  );
}
