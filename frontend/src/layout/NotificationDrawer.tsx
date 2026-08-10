/**
 * NotificationDrawer — right-side slide-in drawer for system notifications.
 *
 * Sourced from the live /api/alerts/ feed (abnormal lab results + active patient
 * alerts). Polls every 15 seconds. Read/unread state is local to the session.
 */

import {
  ActionIcon,
  Badge,
  Box,
  Button,
  Drawer,
  Group,
  Indicator,
  ScrollArea,
  Stack,
  Text,
  ThemeIcon,
  Title,
} from "@mantine/core";
import {
  IconBell,
  IconCheck,
} from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import dayjs from "dayjs";
import relativeTime from "dayjs/plugin/relativeTime";
import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { fetchAlerts } from "@/api/endpoints";
import type { AlertFeedItem } from "@/types";

dayjs.extend(relativeTime);

interface Notification {
  id: string;
  type: "lab" | "referral" | "appointment" | "system" | "alert";
  title: string;
  description: string;
  timestamp: string;
  link: string;
  read: boolean;
  severity?: string;
}

function alertToNotification(a: AlertFeedItem): Notification {
  const type = a.kind === "LAB_ABNORMAL" ? "lab"
             : a.kind === "ALLERGY"      ? "alert"
             : "system";
  return {
    id:          a.id,
    type,
    title:       a.label,
    description: a.detail,
    timestamp:   a.timestamp,
    link:        a.patient_nhid ? `/patients/${a.patient_nhid}` : "/alerts",
    read:        !a.is_active,
    severity:    a.severity,
  };
}

export function NotificationDrawer() {
  const navigate = useNavigate();
  const [opened, setOpened]               = useState(false);
  const [readIds, setReadIds]             = useState<Set<string>>(new Set());
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [badgeCleared, setBadgeCleared]   = useState(false);

  const { data: alertsData } = useQuery({
    queryKey: ["alerts-bell"],
    queryFn:  () => fetchAlerts().then((r) => r.data),
    refetchInterval: 15_000,
    staleTime:       10_000,
  });

  // Merge real alerts into notifications list (avoid duplicates)
  useEffect(() => {
    if (!alertsData?.results) return;
    const realNotifs = alertsData.results.map(alertToNotification);
    setNotifications((prev) => {
      const existingIds = new Set(prev.map((n) => n.id));
      const newOnes = realNotifs.filter((n) => !existingIds.has(n.id));
      return [...newOnes, ...prev];
    });
  }, [alertsData]);

  // When drawer opens, clear the badge count visually
  useEffect(() => {
    if (opened) {
      setBadgeCleared(true);
    }
  }, [opened]);

  // Reset badge clearing when new notifications arrive
  useEffect(() => {
    setBadgeCleared(false);
  }, [notifications.length]);

  const unreadCount = notifications.filter(
    (n) => !n.read && !readIds.has(n.id)
  ).length;

  const displayCount = badgeCleared ? 0 : unreadCount;

  function markRead(id: string) {
    setReadIds((prev) => new Set([...prev, id]));
  }

  function markAllRead() {
    setReadIds(new Set(notifications.map((n) => n.id)));
  }

  function handleClick(n: Notification) {
    markRead(n.id);
    setOpened(false);
    navigate(n.link);
  }

  return (
    <>
      {/* Bell icon with badge — triggers drawer */}
      <Indicator
        color="red"
        label={displayCount > 9 ? "9+" : String(displayCount)}
        size={16}
        disabled={displayCount === 0}
        offset={4}
      >
        <ActionIcon
          variant="subtle"
          size="lg"
          aria-label={`${displayCount} notifications`}
          onClick={() => setOpened(true)}
        >
          <IconBell size={18} />
        </ActionIcon>
      </Indicator>

      {/* Drawer */}
      <Drawer
        opened={opened}
        onClose={() => setOpened(false)}
        position="right"
        size={320}
        padding={0}
        title={
          <Group justify="space-between" px="md" pt="md" w="100%">
            <Group gap="xs">
              <ThemeIcon size={28} radius="md" color="medsync" variant="light">
                <IconBell size={16} />
              </ThemeIcon>
              <Title order={4} style={{ fontSize: "16px", fontWeight: 600 }}>Notifications</Title>
              {unreadCount > 0 && (
                <Badge color="red" size="sm" variant="filled">{unreadCount}</Badge>
              )}
            </Group>
          </Group>
        }
      >
        <Stack gap={0}>
          {/* Mark all read */}
          <Group justify="flex-end" px="md" py="xs" style={{ borderBottom: "1px solid var(--border)" }}>
            <Button
              variant="subtle"
              size="xs"
              leftSection={<IconCheck size={14} />}
              onClick={markAllRead}
              disabled={unreadCount === 0}
            >
              Mark all as read
            </Button>
          </Group>

          {/* Notification list */}
          <ScrollArea h="calc(100vh - 120px)" px="md">
            <Stack gap="xs" py="sm">
              {notifications.length === 0 ? (
                <Box ta="center" py="xl">
                  <Text c="dimmed" size="sm">No notifications yet.</Text>
                </Box>
              ) : (
                notifications.map((n) => {
                  const isRead = n.read || readIds.has(n.id);
                  
                  // Color dot matching EMR specs: red=critical, amber=warning, blue=info, green=success
                  const dotColor = 
                    n.severity === "critical" || n.type === "alert" ? "var(--accent-red)" :
                    n.severity === "warning" ? "var(--accent-amber)" :
                    n.severity === "success" ? "var(--accent-green)" :
                    "var(--accent-blue)";

                  return (
                    <Box
                      key={n.id}
                      onClick={() => handleClick(n)}
                      style={{
                        cursor: "pointer",
                        borderRadius: "var(--radius)",
                        padding: "10px 12px",
                        background: isRead
                          ? undefined
                          : "var(--surface-0)",
                        border: `1px solid ${isRead ? "var(--border)" : "var(--border-strong)"}`,
                        transition: "background 0.1s",
                      }}
                    >
                      <Group gap="xs" align="flex-start" wrap="nowrap">
                        {/* Colored left dot */}
                        <div
                          style={{
                            width: 8,
                            height: 8,
                            borderRadius: "50%",
                            backgroundColor: dotColor,
                            flexShrink: 0,
                            marginTop: 6,
                          }}
                        />
                        
                        <Box style={{ flex: 1, minWidth: 0 }}>
                          <Group justify="space-between" wrap="nowrap" gap="xs">
                            <Text size="sm" fw={isRead ? 400 : 700} lineClamp={1} c="var(--text-primary)">
                              {n.title}
                            </Text>
                          </Group>
                          <Text size="xs" c="var(--text-secondary)" lineClamp={1} mt={2}>
                            {n.description}
                          </Text>
                          <Text size="xs" c="var(--text-muted)" mt={4}>
                            {dayjs(n.timestamp).fromNow()}
                          </Text>
                        </Box>
                      </Group>
                    </Box>
                  );
                })
              )}
            </Stack>
          </ScrollArea>
        </Stack>
      </Drawer>
    </>
  );
}
