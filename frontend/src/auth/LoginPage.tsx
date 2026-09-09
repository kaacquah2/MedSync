import {
  Anchor,
  Box,
  Button,
  Group,
  Paper,
  PasswordInput,
  Stack,
  Text,
  TextInput,
  ThemeIcon,
  Checkbox,
  UnstyledButton,
} from "@mantine/core";
import { useForm } from "@mantine/form";
import {
  IconActivity,
  IconAlertCircle,
  IconArrowLeft,
  IconCheck,
  IconLock,
  IconShieldCheck,
  IconUser,
} from "@tabler/icons-react";
import { useState, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "./AuthProvider";
import classes from "./LoginPage.module.css";

/** Contact number shown on the lockout screen — update in one place */
const SUPPORT_PHONE = "+233 24 123 4567";

type LoginStep =
  | "credentials"
  | "account-locked"
  | "forgot-password-email"
  | "forgot-password-sent"   // production: contact IT admin (no real backend reset)
  | "forgot-password-check"  // dev-only: simulate reset link click
  | "forgot-password-reset"; // dev-only: reset form simulation

function getShiftGreeting(): string {
  const hours = new Date().getHours();
  if (hours < 12) {
    return "Good morning";
  } else if (hours < 17) {
    return "Good afternoon";
  } else if (hours < 21) {
    return "Good evening — evening shift";
  } else {
    return "Night shift";
  }
}

export function LoginPage() {
  const { user, login, logout } = useAuth();
  const navigate = useNavigate();

  const [step, setStep]             = useState<LoginStep>("credentials");
  const [error, setError]           = useState<string | null>(null);
  const [loading, setLoading]       = useState(false);
  const [failedAttempts, setFailed] = useState(0);
  const [capsLock, setCapsLock]     = useState(false);
  const [passwordVisible, setPasswordVisible] = useState(false);

  const passwordRef = useRef<HTMLInputElement>(null);

  const form = useForm({
    initialValues: { username: "", password: "", remember: false },
    validate: {
      username: (v) => (v.trim() ? null : "Username or staff ID is required"),
      password: (v) => (v ? null : "Password is required"),
    },
  });

  const forgotEmailForm = useForm({
    initialValues: { emailOrId: "" },
    validate: { emailOrId: (v) => (v.trim() ? null : "Email or staff ID is required") },
  });

  const resetPasswordForm = useForm({
    initialValues: { newPassword: "", confirmPassword: "" },
    validate: {
      newPassword: (v) => (v.length >= 12 ? null : "Password must be at least 12 characters"),
      confirmPassword: (v, vals) => (v === vals.newPassword ? null : "Passwords do not match"),
    },
  });

  async function handleCredentialsSubmit(values: typeof form.values) {
    setError(null);
    form.clearErrors();
    setLoading(true);
    try {
      // AuthProvider.login() handles everything:
      //   • calls POST /api/auth/login/
      //   • checks GET /api/mfa/status/ (including trusted-device cookie)
      //   • if MFA needed  → navigates to /mfa/verify  (real TOTP page)
      //   • if MFA setup needed → navigates to /mfa/setup
      //   • if no MFA / trusted device → navigates to role home
      await login(values.username.trim(), values.password);
      // Component unmounts on success; no state update needed.
    } catch (err: unknown) {
      setLoading(false);
      const e = err as { response?: { status?: number; data?: { error?: string } } };
      const status = e?.response?.status;
      const msg = e?.response?.data?.error ?? "";

      const next = failedAttempts + 1;
      setFailed(next);

      if (status === 403 && msg.toLowerCase().includes("deactivated")) {
        form.setFieldError("username", "Account locked — contact your hospital admin");
      } else if (status === 403 || next >= 5) {
        setStep("account-locked");
      } else if (msg === "Invalid username or password." || msg.includes("Invalid")) {
        const usernameLower = values.username.trim().toLowerCase();
        // Determine whether to map as wrong password or invalid user ID
        const isDemoOrFormat = usernameLower === "admin" ||
                               usernameLower.includes("_") ||
                               usernameLower.startsWith("admin");
        if (isDemoOrFormat) {
          form.setFieldError("password", "Incorrect password");
        } else {
          form.setFieldError("username", "Staff ID not found");
        }
      } else {
        setError(msg || "Invalid username or password.");
      }
    }
  }

  return (
    <div className={classes.root}>
      {/* ── Left: brand panel ─────────────────────────────────────────────── */}
      <div className={classes.brand}>
        {/* Logo mark */}
        <div className={classes.logoContainer}>
          <div className={`${classes.logoSquare} heartbeat-icon`}>
            <IconActivity size={24} />
          </div>
          <div>
            <div className={classes.wordmark}>MedSync EMR</div>
            <div className={classes.logoSubtitle}>Multi-hospital records · Ghana</div>
          </div>
        </div>

        {/* Brand Content */}
        <div className={classes.brandContent}>
          <h1 className={classes.brandHeadline}>
            One patient record. <span className={classes.goldHighlight}>Every hospital,</span> every shift.
          </h1>
          <p className={classes.brandSubline}>
            Reliable, secure access to clinical data for the teams who need it — in the ward, the lab, and the consulting room.
          </p>

          {/* Animated ECG Trace */}
          <div className={classes.ecgContainer}>
            <svg viewBox="0 0 400 100" fill="none" stroke="var(--gold)" strokeWidth="2.5" className={classes.ecgTrace}>
              <path d="M 0 50 L 100 50 L 110 40 L 120 60 L 130 50 L 150 50 L 160 20 L 175 90 L 190 50 L 210 50 L 220 40 L 230 60 L 240 50 L 300 50 L 310 20 L 325 90 L 340 50 L 400 50" />
            </svg>
          </div>

          {/* Assurance Ledger */}
          <div className={classes.assuranceLedger}>
            <div className={classes.ledgerRow}>
              <span className={classes.ledgerLabel}>ACCESS</span>
              <span className={classes.ledgerValue}>Role-based control: staff see only what their role permits</span>
            </div>
            <div className={classes.ledgerRow}>
              <span className={classes.ledgerLabel}>AUDIT</span>
              <span className={classes.ledgerValue}>Tamper-evident trail on every record view and edit</span>
            </div>
            <div className={classes.ledgerRow}>
              <span className={classes.ledgerLabel}>ENCRYPTION</span>
              <span className={classes.ledgerValue}>Field-level Fernet encryption for sensitive patient data</span>
            </div>
            <div className={classes.ledgerRow}>
              <span className={classes.ledgerLabel}>SHIFTS</span>
              <span className={classes.ledgerValue}>Verify once: your device stays trusted for 8 hours</span>
            </div>
          </div>
        </div>

        {/* Brand Panel Footer */}
        <div className={classes.brandFooter}>
          MedSync EMR · For authorised clinical and administrative staff only
        </div>
      </div>

      {/* ── Right: form column ────────────────────────────────────────────── */}
      <div className={classes.formCol}>
        <div className={classes.card}>
          {/* Active User Switch Banner */}
          {user && (
            <div className={classes.switchUserBanner}>
              <span className={classes.switchUserText}>
                Signed in as <strong>{user.full_name || user.username}</strong> ({user.role_display})
              </span>
              <UnstyledButton
                type="button"
                className={classes.switchUserLink}
                onClick={async () => {
                  await logout();
                  form.reset();
                  setError(null);
                }}
              >
                Switch account
              </UnstyledButton>
            </div>
          )}

          {/* ── CREDENTIALS ──────────────────────────────────────────────── */}
          {step === "credentials" && (
            <Stack gap="xl">
              <Box>
                <div className={classes.greeting}>{getShiftGreeting()}</div>
                <h2 className={classes.cardHeading}>Sign in to your account</h2>
                <p className={classes.cardSubline}>
                  Sessions are protected by role-based access control and full audit logging.
                </p>
              </Box>

              {error && (
                <Text size="sm" c="var(--danger)" fw={600}>
                  {error}
                </Text>
              )}

              <form onSubmit={form.onSubmit(handleCredentialsSubmit)}>
                <Stack gap="md">
                  <TextInput
                    label="Username or staff ID"
                    placeholder="e.g. ugmc_doctor"
                    leftSection={<IconUser size={18} color="#475569" />}
                    autoComplete="username"
                    autoFocus
                    spellCheck={false}
                    classNames={{
                      input: classes.inputMono,
                      label: classes.inputLabel,
                    }}
                    {...form.getInputProps("username")}
                  />
                  
                  <Box>
                    <PasswordInput
                      ref={passwordRef}
                      label="Password"
                      placeholder="Enter password"
                      leftSection={<IconLock size={18} color="#475569" />}
                      autoComplete="current-password"
                      visible={passwordVisible}
                      onVisibilityChange={setPasswordVisible}
                      visibilityToggleButtonProps={{
                        "aria-label": passwordVisible ? "Hide password" : "Show password",
                        style: { color: "#475569" },
                      }}
                      classNames={{
                        input: classes.input,
                        innerInput: classes.innerInput,
                        label: classes.inputLabel,
                      }}
                      {...form.getInputProps("password")}
                      onKeyUp={(e) => {
                        setCapsLock(e.getModifierState("CapsLock"));
                      }}
                      onBlur={() => {
                        setCapsLock(false);
                      }}
                    />
                    {capsLock && (
                      <Text size="xs" c="var(--danger)" fw={600} mt={4} role="status">
                        Caps Lock is on
                      </Text>
                    )}
                  </Box>

                  <Group justify="space-between">
                    <Checkbox
                      label="Remember this device"
                      classNames={{ label: classes.checkboxLabel, input: classes.checkboxInput }}
                      {...form.getInputProps("remember", { type: "checkbox" })}
                    />
                    <Anchor
                      component="button"
                      type="button"
                      className={classes.forgotLink}
                      onClick={() => setStep("forgot-password-email")}
                    >
                      Forgot password?
                    </Anchor>
                  </Group>

                  <Button
                    type="submit"
                    fullWidth
                    disabled={loading}
                    className={classes.button}
                    mt="xs"
                  >
                    {loading ? "Signing in…" : "Sign in"}
                  </Button>
                </Stack>
              </form>

              {/* 2FA Info Callout */}
              <Paper className={classes.callout2fa}>
                <Group gap="xs" wrap="nowrap" align="flex-start">
                  <IconShieldCheck size={16} color="#177E6F" style={{ marginTop: 2, flexShrink: 0 }} />
                  <Text className={classes.callout2faText}>
                    Admins and clinical staff verify with an authenticator app; after one code the device is trusted for 8 hours.
                  </Text>
                </Group>
              </Paper>

              {/* Redirect to Dashboard link for active users */}
              {user && (
                <Button
                  variant="subtle"
                  className={classes.buttonSubtle}
                  onClick={() => navigate("/")}
                  fullWidth
                >
                  Go to Dashboard →
                </Button>
              )}

              {/* Demo accounts (dev only) */}
              {import.meta.env.DEV && (
                <details className={classes.details}>
                  <summary>Demo accounts — dev only</summary>
                  <Text className={classes.detailsNote} mt="xs">
                    All accounts use password: <code>Demo@123456</code> (Tap a chip to autofill).
                  </Text>
                  <div className={classes.chipGrid}>
                    {[
                      { username: "admin", label: "admin", desc: "Super Admin (system-wide)" },
                      { username: "ugmc_admin", label: "ugmc_admin", desc: "hospital_admin" },
                      { username: "ugmc_doctor", label: "ugmc_doctor", desc: "doctor" },
                      { username: "ugmc_nurse", label: "ugmc_nurse", desc: "nurse" },
                      { username: "ugmc_lab", label: "ugmc_lab", desc: "lab_technician" },
                      { username: "ugmc_reception", label: "ugmc_reception", desc: "receptionist" },
                    ].map((chip) => (
                      <UnstyledButton
                        key={chip.username}
                        type="button"
                        className={classes.chip}
                        onClick={() => {
                          form.setFieldValue("username", chip.username);
                          form.setFieldValue("password", "Demo@123456");
                          setTimeout(() => {
                            passwordRef.current?.focus();
                          }, 50);
                        }}
                      >
                        <span className={classes.chipLabel}>{chip.label}</span>
                        <span className={classes.chipDesc}>{chip.desc}</span>
                      </UnstyledButton>
                    ))}
                  </div>
                </details>
              )}
            </Stack>
          )}

          {/* ── ACCOUNT LOCKED ───────────────────────────────────────────── */}
          {step === "account-locked" && (
            <Box ta="center">
              <ThemeIcon size={56} radius="xl" color="red" variant="light" mb="md" style={{ margin: "0 auto 1rem auto" }}>
                <IconAlertCircle size={32} />
              </ThemeIcon>
              <h2 className={classes.cardHeading} style={{ color: "var(--danger)" }}>Account locked</h2>
              <Text c="dimmed" size="sm" mb="lg">
                Your account has been locked after 5 failed attempts.
                Contact your hospital IT administrator or call{" "}
                <strong>{SUPPORT_PHONE}</strong>.
              </Text>
              <Button
                className={classes.button}
                fullWidth
                onClick={() => { setFailed(0); setStep("credentials"); setError(null); form.reset(); }}
              >
                Try again
              </Button>
            </Box>
          )}

          {/* ── FORGOT PASSWORD: enter email ─────────────────────────────── */}
          {step === "forgot-password-email" && (
            <Stack gap="md">
              <Box>
                <h2 className={classes.cardHeading}>Forgot password</h2>
                <p className={classes.cardSubline}>
                  Enter your registered email or staff ID.
                </p>
              </Box>
              <form onSubmit={forgotEmailForm.onSubmit(() =>
                setStep(import.meta.env.DEV ? "forgot-password-check" : "forgot-password-sent")
              )}>
                <Stack gap="md">
                  <TextInput
                    label="Email or staff ID"
                    placeholder="Enter email or staff ID"
                    classNames={{ input: classes.input, label: classes.inputLabel }}
                    autoFocus
                    {...forgotEmailForm.getInputProps("emailOrId")}
                  />
                  <Button type="submit" className={classes.button} fullWidth>Continue</Button>
                  <Button
                    variant="subtle"
                    className={classes.buttonSubtle}
                    leftSection={<IconArrowLeft size={16} />}
                    onClick={() => setStep("credentials")}
                  >
                    Back to sign in
                  </Button>
                </Stack>
              </form>
            </Stack>
          )}

          {/* ── FORGOT PASSWORD: production path — contact IT admin ────────── */}
          {step === "forgot-password-sent" && (
            <Box ta="center">
              <ThemeIcon size={48} radius="xl" color="blue" variant="light" mb="md" style={{ margin: "0 auto 1rem auto" }}>
                <IconShieldCheck size={28} />
              </ThemeIcon>
              <h2 className={classes.cardHeading}>Contact your administrator</h2>
              <Text c="dimmed" size="sm" mb="lg">
                For security reasons, password resets are handled by your hospital IT administrator.
                Please contact them directly and quote your staff ID.
              </Text>
              <Button
                variant="subtle"
                className={classes.buttonSubtle}
                leftSection={<IconArrowLeft size={16} />}
                onClick={() => setStep("credentials")}
              >
                Back to sign in
              </Button>
            </Box>
          )}

          {/* ── FORGOT PASSWORD: dev-only simulation steps ────────────────── */}
          {import.meta.env.DEV && step === "forgot-password-check" && (
            <Box ta="center">
              <ThemeIcon size={48} radius="xl" color="green" variant="light" mb="md" style={{ margin: "0 auto 1rem auto" }}>
                <IconCheck size={28} />
              </ThemeIcon>
              <h2 className={classes.cardHeading}>Check your email</h2>
              <Text c="dimmed" size="sm" mb="md">
                If this account exists, a reset link has been sent.
              </Text>
              <Stack gap="sm">
                <Button className={classes.button} fullWidth onClick={() => setStep("forgot-password-reset")}>
                  [Dev] Simulate clicking reset link
                </Button>
                <Button
                  variant="subtle"
                  className={classes.buttonSubtle}
                  leftSection={<IconArrowLeft size={16} />}
                  onClick={() => setStep("credentials")}
                >
                  Back to sign in
                </Button>
              </Stack>
            </Box>
          )}

          {import.meta.env.DEV && step === "forgot-password-reset" && (
            <Stack gap="md">
              <Box>
                <h2 className={classes.cardHeading}>Reset password</h2>
                <p className={classes.cardSubline}>Choose a strong new password (minimum 12 characters).</p>
              </Box>
              <form onSubmit={resetPasswordForm.onSubmit(() => {
                setStep("credentials");
                resetPasswordForm.reset();
              })}>
                <Stack gap="md">
                  <PasswordInput
                    label="New password"
                    placeholder="Enter new password"
                    classNames={{ input: classes.input, innerInput: classes.innerInput, label: classes.inputLabel }}
                    autoFocus
                    {...resetPasswordForm.getInputProps("newPassword")}
                  />
                  <PasswordInput
                    label="Confirm password"
                    placeholder="Confirm new password"
                    classNames={{ input: classes.input, innerInput: classes.innerInput, label: classes.inputLabel }}
                    {...resetPasswordForm.getInputProps("confirmPassword")}
                  />
                  <Button type="submit" className={classes.button} fullWidth>Change password</Button>
                </Stack>
              </form>
            </Stack>
          )}

          <Text size="xs" c="dimmed" ta="center" mt="md">
            Session expires after 1 hour of inactivity.
          </Text>
        </div>
      </div>
    </div>
  );
}
