/**
 * Main application shell — Mantine AppShell with:
 *  - Header: brand, global NHID search (/ shortcut), dark-mode toggle, user menu
 *  - Navbar: role-sectioned nav from NAV_BY_ROLE, idle-timeout guard
 *
 * Fix applied (Phase A): was importing non-existent NAV_ITEMS (flat) and
 * comparing roles as UPPERCASE strings. Now correctly uses NAV_BY_ROLE
 * (sectioned) and ROLE_COLORS (snake_case keys).
 */

import {
  ActionIcon,
  AppShell,
  Avatar,
  Badge,
  Box,
  Burger,
  Button,
  Card,
  Group,
  Menu,
  Modal,
  ScrollArea,
  Text,
  TextInput,
  ThemeIcon,
  Tooltip,
  UnstyledButton,
  useMantineColorScheme,
  Progress,
  Stack,
} from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import classes from "./AppLayout.module.css";
import {
  IconActivity,
  IconAlertTriangle,
  IconArrowLeftRight,
  IconBed,
  IconBrain,
  IconBuilding,
  IconCalendar,
  IconChartBar,
  IconClipboardList,
  IconClock,
  IconFlask,
  IconHeartbeat,
  IconLayoutDashboard,
  IconLogout,
  IconMoon,
  IconNetwork,
  IconPill,
  IconSearch,
  IconShieldLock,
  IconSun,
  IconUrgent,
  IconUser,
  IconUserPlus,
  IconUsers,
  IconEye,
  IconEyeOff,
} from "@tabler/icons-react";
import { useEffect, useRef, useState } from "react";
import { NavLink as RouterNavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "@/auth/AuthProvider";
import { fetchAlerts, fetchCsrf, fetchDashboard, fetchShifts } from "@/api/endpoints";
import { ROLE_COLORS } from "@/constants/roles";
import { OfflineBanner } from "@/components/OfflineBanner";
import { NotificationDrawer } from "./NotificationDrawer";
import { NAV_BY_ROLE } from "./navItems";

// Maps the string icon-names stored in navItems.ts to real Tabler components.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const ICON_MAP: Record<string, React.ComponentType<any>> = {
  IconActivity,
  IconAlertTriangle,
  IconArrowLeftRight,
  IconBed,
  IconBrain,
  IconBuilding,
  IconCalendar,
  IconChartBar,
  IconClipboardList,
  IconClock,
  IconFlask,
  IconHeartbeat,
  IconLayoutDashboard,
  IconNetwork,
  IconPill,
  IconSearch,
  IconShieldLock,
  IconUrgent,
  IconUserPlus,
  IconUsers,
};

// Idle timeout constants (ms).
// LOGOUT_AT_MS must equal Django's SESSION_COOKIE_AGE (emr/settings.py, default 900 s).
// If SESSION_COOKIE_AGE changes, update LOGOUT_AT_MS to match.
// Enforces 15-minute clinical inactivity limit pursuant to HIPAA § 164.312(a)(2)(iii).
export const SESSION_DURATION_MS = 15 * 60 * 1000; // 900 s (15 min) — mirrors SESSION_COOKIE_AGE
export const WARN_BEFORE_MS      =  2 * 60 * 1000; // warn 2 minutes before expiry
export const WARN_AT_MS          = SESSION_DURATION_MS - WARN_BEFORE_MS;
export const LOGOUT_AT_MS        = SESSION_DURATION_MS;
export const COUNTDOWN_MS        = WARN_BEFORE_MS;

import { useQuery } from "@tanstack/react-query";

interface RolePillInfo {
  color: string;
  label: string;
}

function getRolePillInfo(role: string): RolePillInfo {
  switch (role) {
    case "super_admin":
      return { color: "var(--danger)", label: "SUPER ADMIN" };
    case "hospital_admin":
      return { color: "var(--gold)", label: "HOSPITAL ADMIN" };
    case "doctor":
      return { color: "var(--accent)", label: "DOCTOR" };
    case "nurse":
      return { color: "var(--ok)", label: "NURSE" };
    case "lab_technician":
      return { color: "#2B6CB0", label: "LAB TECHNICIAN" };
    case "receptionist":
      return { color: "var(--muted)", label: "RECEPTIONIST" };
    default:
      return { color: "var(--muted)", label: String(role).toUpperCase() };
  }
}

export function AppLayout() {
  const [opened, { toggle, close }]             = useDisclosure(false);
  const [sessionWarn, { open: openWarn, close: closeWarn }] = useDisclosure(false);
  const [countdown, setCountdown]               = useState(COUNTDOWN_MS / 1000);
  const { user, logout }                        = useAuth();
  const navigate                                = useNavigate();
  const { colorScheme, toggleColorScheme }      = useMantineColorScheme();
  const [searchQuery, setSearchQuery]           = useState("");
  const searchRef                               = useRef<HTMLInputElement>(null);

  const [curtainMode, setCurtainMode]           = useState(false);

  // Keyboard shortcut: Alt+P to toggle Ward Privacy Screen
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.altKey && (e.key === "p" || e.key === "P")) {
        e.preventDefault();
        setCurtainMode((prev) => !prev);
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  const isNurse = user?.role === "nurse";

  // Shift tracking for clinical ward nurses: driven by authentic database ShiftRecord
  const { data: shiftsData } = useQuery({
    queryKey: ["active-shift-nurse", user?.id],
    queryFn: () => fetchShifts().then((r) => r.data),
    staleTime: 30_000,
    refetchInterval: 60_000,
    enabled: !!user && isNurse,
  });

  const activeShift = isNurse ? (shiftsData?.find((s) => s.is_active) ?? null) : null;
  const [shiftProgress, setShiftProgress] = useState(100);
  const [shiftTimeLeft, setShiftTimeLeft] = useState("Off duty");

  useEffect(() => {
    if (!isNurse || !activeShift?.started_at) {
      setShiftProgress(0);
      setShiftTimeLeft("Off duty");
      return;
    }

    const shiftStart = new Date(activeShift.started_at).getTime();

    const updateTimer = () => {
      const duration = 8 * 60 * 60 * 1000; // 8 hours
      const elapsed = Date.now() - shiftStart;
      const remaining = duration - elapsed;

      if (remaining <= 0) {
        setShiftProgress(0);
        setShiftTimeLeft("0h 00m");
      } else {
        const pct = Math.max(0, Math.min(100, (remaining / duration) * 100));
        setShiftProgress(pct);

        const totalMinutes = Math.floor(remaining / (60 * 1000));
        const hours = Math.floor(totalMinutes / 60);
        const minutes = totalMinutes % 60;
        setShiftTimeLeft(`${hours}h ${String(minutes).padStart(2, "0")}m`);
      }
    };

    updateTimer();
    const interval = setInterval(updateTimer, 30000);
    return () => clearInterval(interval);
  }, [isNurse, activeShift?.started_at]);

  // Sync colorScheme to data-mode attribute for the CSS custom variables
  useEffect(() => {
    const root = document.documentElement;
    root.setAttribute("data-mode", colorScheme);
    localStorage.setItem("mEd-theme", colorScheme);
  }, [colorScheme]);

  // Sidebar badge queries
  const { data: alertsData } = useQuery({
    queryKey: ["alerts-bell"],
    queryFn:  () => fetchAlerts().then((r) => r.data),
    refetchInterval: 15_000,
    staleTime:       10_000,
    enabled:         !!user,
  });
  const unreadAlertsCount = alertsData?.results?.filter((a) => a.is_active).length ?? 0;

  const { data: dashboardData } = useQuery({
    queryKey: ["dashboard"],
    queryFn:  () => fetchDashboard().then((r) => r.data),
    staleTime: 2 * 60 * 1000,
    enabled:         !!user,
  });
  const worklistCount = dashboardData?.recent_encounters?.length ?? 0;

  // ── "/" keyboard shortcut to focus global search ──────────────────────────
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (
        e.key === "/" &&
        !(e.target instanceof HTMLInputElement) &&
        !(e.target instanceof HTMLTextAreaElement)
      ) {
        e.preventDefault();
        searchRef.current?.focus();
      }
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, []);

  // ── Session idle timeout ──────────────────────────────────────────────────
  useEffect(() => {
    let warnTimer:   ReturnType<typeof setTimeout>;
    let logoutTimer: ReturnType<typeof setTimeout>;
    let countdownInterval: ReturnType<typeof setInterval>;
    let warningShown = false;

    function resetTimers() {
      clearTimeout(warnTimer);
      clearTimeout(logoutTimer);
      clearInterval(countdownInterval);
      warningShown = false;
      closeWarn();
      setCountdown(COUNTDOWN_MS / 1000);

      warnTimer = setTimeout(() => {
        if (warningShown) return;
        warningShown = true;
        openWarn();
        setCountdown(COUNTDOWN_MS / 1000);
        // tick countdown every second
        countdownInterval = setInterval(() => {
          setCountdown((c) => (c > 0 ? c - 1 : 0));
        }, 1000);
      }, WARN_AT_MS);

      logoutTimer = setTimeout(async () => {
        clearInterval(countdownInterval);
        closeWarn();
        await logout();
        navigate("/login", { replace: true });
      }, LOGOUT_AT_MS);
    }

    // Autonomous background heartbeat removed to prevent indefinite session prolongation.
    // Session extension occurs only in response to verified user interactions.
    const events = ["mousemove", "keydown", "click", "scroll", "touchstart"];
    events.forEach((ev) => document.addEventListener(ev, resetTimers, { passive: true }));
    resetTimers();

    return () => {
      clearTimeout(warnTimer);
      clearTimeout(logoutTimer);
      clearInterval(countdownInterval);
      events.forEach((ev) => document.removeEventListener(ev, resetTimers));
    };
  }, [logout, navigate, openWarn, closeWarn]);

  function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    const q = searchQuery.trim();
    if (q) {
      if (/^NHID-[A-F0-9]{8,16}$/i.test(q)) {
        // Direct route navigation prevents leaving sensitive patient NHIDs in URL query strings
        navigate(`/patients/${q.toUpperCase()}`);
      } else {
        // Pass search query via navigation state to avoid leaving sensitive patient names/IDs in URL query strings
        navigate("/patients", { state: { q } });
      }
      setSearchQuery("");
      close();
    }
  }

  async function handleLogout() {
    await logout();
    navigate("/login", { replace: true });
  }

  // Role-specific nav sections and colour — both keyed by snake_case Role
  const userNav   = NAV_BY_ROLE[user!.role] ?? [];
  const roleColor = ROLE_COLORS[user!.role] ?? "blue";

  // Alert bell polling — 30s interval, scoped to user's hospital

  const rolePill = getRolePillInfo(user!.role);

  return (
    <>
      <AppShell
      header={{ height: 60 }}
      navbar={{
        width: 240,
        breakpoint: "lg",
        collapsed: { mobile: !opened, desktop: false }
      }}
      padding="md"
    >
      {/* ── Header ──────────────────────────────────────────────────────────── */}
      <AppShell.Header>
        <Group h="100%" px="md" justify="space-between" wrap="nowrap">
          {/* Left: burger + brand */}
          <Group>
            <Burger opened={opened} onClick={toggle} hiddenFrom="lg" size="sm" />
            <RouterNavLink to="/" style={{ textDecoration: "none" }}>
              <Group gap="xs" align="center">
                <ThemeIcon
                  size={34}
                  radius="md"
                  variant="filled"
                  style={{ backgroundColor: "var(--accent)" }}
                >
                  <IconActivity size={20} />
                </ThemeIcon>
                <Text fw={800} size="lg" style={{ fontFamily: "'Bricolage Grotesque', sans-serif", color: "var(--ink)", letterSpacing: "-0.02em" }}>
                  MedSync
                </Text>
                <Tooltip label="Connected to national EMR network">
                  <span className={classes.syncStatusDot} />
                </Tooltip>
              </Group>
            </RouterNavLink>

            {/* Hospital badge */}
            {user?.role !== "super_admin" && user?.hospital && (
              <Badge variant="light" styles={{ root: { backgroundColor: "rgba(23, 126, 111, 0.12)", color: "var(--accent)" } }} visibleFrom="sm">
                {user.hospital.code}
              </Badge>
            )}
          </Group>

          {/* Centre: global patient search (desktop only) */}
          <Box
            component="form"
            onSubmit={handleSearch}
            style={{ flex: 1, maxWidth: 480 }}
            mx="xl"
            visibleFrom="sm"
          >
            <TextInput
              ref={searchRef}
              placeholder="Search patients by name or NHID (press / to focus)"
              leftSection={<IconSearch size={16} />}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.currentTarget.value)}
              styles={{
                input: {
                  borderRadius: "14px",
                  border: "1px solid var(--line)",
                  backgroundColor: "var(--card)",
                  color: "var(--text)",
                }
              }}
              size="md"
            />
          </Box>

          {/* Right: notification drawer + curtain mode + theme toggle + user menu */}
          <Group>
            <Tooltip label={curtainMode ? "Disable Ward Privacy Screen (Alt+P)" : "Ward Privacy Screen / Curtain Mode (Alt+P)"}>
              <ActionIcon
                onClick={() => setCurtainMode(!curtainMode)}
                variant={curtainMode ? "filled" : "subtle"}
                color={curtainMode ? "grape" : "gray"}
                size="lg"
                aria-label="Toggle Ward Privacy Screen"
              >
                {curtainMode ? <IconEyeOff size={18} /> : <IconEye size={18} />}
              </ActionIcon>
            </Tooltip>

            <NotificationDrawer />

            <Tooltip label={colorScheme === "dark" ? "Light mode" : "Dark mode"}>
              <ActionIcon onClick={() => toggleColorScheme()} variant="subtle" size="lg">
                {colorScheme === "dark" ? <IconSun size={18} /> : <IconMoon size={18} />}
              </ActionIcon>
            </Tooltip>

            <Menu shadow="md" width={220}>
              <Menu.Target>
                <UnstyledButton className={classes.userChip}>
                  <Group gap="xs" wrap="nowrap">
                    <Avatar radius="xl" size="sm" color={roleColor}>
                      {user?.first_name?.[0] ?? user?.username?.[0] ?? "?"}
                    </Avatar>
                    <Box visibleFrom="sm">
                      <Text size="sm" fw={600} lh={1.2}>
                        {user?.full_name || user?.username}
                      </Text>
                      <Text size="xs" c="var(--muted)">{user?.role_display}</Text>
                    </Box>
                  </Group>
                </UnstyledButton>
              </Menu.Target>

              <Menu.Dropdown styles={{ dropdown: { borderRadius: "14px", border: "1px solid var(--line)", padding: "0.5rem" } }}>
                <Menu.Label style={{ padding: "0.5rem" }}>
                  <Text size="sm" fw={700} c="var(--text)">
                    {user?.full_name || user?.username}
                  </Text>
                  <Text size="xs" c="var(--muted)">
                    {user?.role_display}
                  </Text>
                  {user?.hospital && (
                    <Text size="xs" c="var(--accent)" fw={500} mt={2}>
                      Scope: {user.hospital.name} ({user.hospital.code})
                    </Text>
                  )}
                </Menu.Label>
                <Menu.Divider style={{ margin: "0.5rem 0" }} />
                <Menu.Item
                  leftSection={<IconUser size={16} />}
                  onClick={() => navigate("/profile")}
                  style={{ borderRadius: "8px" }}
                >
                  My Profile
                </Menu.Item>
                <Menu.Divider style={{ margin: "0.5rem 0" }} />
                <Menu.Item
                  color="red"
                  leftSection={<IconLogout size={16} />}
                  onClick={handleLogout}
                  style={{ borderRadius: "8px" }}
                >
                  Sign Out
                </Menu.Item>
              </Menu.Dropdown>
            </Menu>
          </Group>
        </Group>
      </AppShell.Header>

      {/* ── Navbar ──────────────────────────────────────────────────────────── */}
      <AppShell.Navbar p="xs">
        <ScrollArea style={{ flex: 1 }}>
          <Box mt="xs">
            {/* Mobile search */}
            <Box component="form" onSubmit={handleSearch} mb="sm" hiddenFrom="lg">
              <TextInput
                placeholder="Search patients…"
                leftSection={<IconSearch size={16} />}
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.currentTarget.value)}
                styles={{
                  input: {
                    borderRadius: "14px",
                    border: "1px solid var(--line)",
                    backgroundColor: "var(--card)",
                    color: "var(--text)",
                  }
                }}
                size="sm"
              />
            </Box>

            {/* Role-sectioned navigation */}
            {userNav.map((section) => (
              <Box key={section.section} mb="xs">
                <div className={classes.navSectionLabel}>
                  {section.section}
                </div>
                {section.items.map((item) => {
                  const Icon = ICON_MAP[item.icon];
                  
                  // Custom logic for pending badge count per EMR specifications
                  let badgeCount = 0;
                  const labelLower = item.label.toLowerCase();
                  if (labelLower === "alerts" || labelLower === "critical values") {
                    badgeCount = unreadAlertsCount;
                  } else if (labelLower === "my worklist" || labelLower === "order worklist") {
                    badgeCount = worklistCount;
                  }

                  return (
                    <RouterNavLink
                      key={item.path}
                      to={item.path}
                      end={item.end}
                      className={({ isActive }) => `${classes.navItem} ${isActive ? classes.navItemActive : ""}`}
                      onClick={close}
                    >
                      {Icon ? <Icon size={18} /> : null}
                      <span>{item.label}</span>
                      {badgeCount > 0 && (
                        <div className={classes.navBadge}>{badgeCount}</div>
                      )}
                    </RouterNavLink>
                  );
                })}
              </Box>
            ))}
          </Box>
        </ScrollArea>

        {/* Footer: shift countdown (nurses only) + role badge */}
        <Stack gap={0} style={{ borderTop: "1px solid var(--line)" }}>
          {isNurse && (
            <Box className={classes.shiftTracker}>
              <div className={classes.shiftHeader}>
                <span className={classes.shiftLabel}>
                  {activeShift ? "Shift remaining" : "Shift status"}
                </span>
                <span className={classes.shiftTime}>{shiftTimeLeft}</span>
              </div>
              <Progress
                value={activeShift ? shiftProgress : 0}
                color={activeShift ? "var(--accent)" : "gray"}
                size="xs"
                radius="xl"
              />
            </Box>
          )}
          <Box
            p="xs"
            pt={isNurse ? 0 : "xs"}
            className="role-badge-text"
          >
            <Group px="xs" pb="xs">
              <Badge
                variant="filled"
                size="sm"
                fullWidth
                styles={{
                  root: {
                    backgroundColor: rolePill.color,
                    color: "white",
                    fontFamily: "'IBM Plex Mono', monospace",
                    fontWeight: 600,
                    borderRadius: "14px",
                    textTransform: "uppercase"
                  }
                }}
              >
                {rolePill.label}
              </Badge>
            </Group>
          </Box>
        </Stack>
      </AppShell.Navbar>

      {/* ── Main content ────────────────────────────────────────────────────── */}
      <AppShell.Main
        style={
          curtainMode
            ? {
                filter: "blur(12px)",
                pointerEvents: "none",
                userSelect: "none",
                transition: "filter 0.2s ease-in-out",
              }
            : { transition: "filter 0.2s ease-in-out" }
        }
      >
        <OfflineBanner />
        <Outlet />
      </AppShell.Main>
    </AppShell>

    {/* ── Ward Privacy Curtain Screen Overlay ────────────────────────────── */}
    {curtainMode && (
      <Box
        onClick={() => setCurtainMode(false)}
        style={{
          position: "fixed",
          inset: 0,
          zIndex: 9999,
          backgroundColor: "rgba(0, 0, 0, 0.4)",
          backdropFilter: "blur(4px)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          cursor: "pointer",
        }}
      >
        <Card
          withBorder
          radius="lg"
          p="xl"
          style={{ textAlign: "center", maxWidth: 420, boxShadow: "0 20px 40px rgba(0,0,0,0.3)" }}
          onClick={(e: React.MouseEvent) => e.stopPropagation()}
        >
          <ThemeIcon size={56} radius="xl" color="grape" variant="light" mx="auto" mb="md">
            <IconShieldLock size={32} />
          </ThemeIcon>
          <Text fw={700} size="lg" mb="xs">Ward Privacy Mode Active</Text>
          <Text size="sm" c="dimmed" mb="lg">
            Patient identifiers and clinical notes are obscured to protect patient privacy against shoulder-surfing on shared ward terminals.
          </Text>
          <Button
            color="grape"
            size="md"
            leftSection={<IconEye size={18} />}
            onClick={() => setCurtainMode(false)}
            fullWidth
          >
            Resume Clinical Session (Alt+P)
          </Button>
        </Card>
      </Box>
    )}

    {/* ── Session timeout warning modal ──────────────────────────────────── */}
    <Modal
      opened={sessionWarn}
      onClose={() => {}}
      withCloseButton={false}
      centered
      size="sm"
      title="Session Expiring Soon"
      overlayProps={{ backgroundOpacity: 0.5 }}
    >
      <Text size="sm" mb="md">
        Your session will expire due to inactivity in{" "}
        <Text component="span" fw={800} c="orange">
          {Math.floor(countdown / 60)}:{String(countdown % 60).padStart(2, "0")}
        </Text>
        . Any unsaved work will be lost.
      </Text>
      <Group justify="flex-end" gap="sm">
        <Button
          variant="subtle"
          color="red"
          onClick={async () => { closeWarn(); await logout(); navigate("/login", { replace: true }); }}
        >
          Log out now
        </Button>
        <Button
          onClick={() => {
            // Refresh session on verified active user interaction and reset timers
            fetchCsrf().catch(() => {});
            closeWarn();
            document.dispatchEvent(new MouseEvent("click"));
          }}
        >
          Continue working
        </Button>
      </Group>
    </Modal>
    </>
  );
}
