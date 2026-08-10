/**
 * NetworkMapPage — animated SVG diagram of the hospital referral network.
 * Node positions are computed dynamically from the hospitals API so any
 * number of hospitals renders correctly (not just the original 3).
 */

import {
  Badge,
  Box,
  Button,
  Card,
  Group,
  SimpleGrid,
  Skeleton,
  Stack,
  Text,
  ThemeIcon,
  Title,
} from "@mantine/core";
import { IconBuilding, IconArrowLeftRight, IconRefresh } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { fetchHospitals, fetchReferrals } from "@/api/endpoints";
import type { Hospital, Referral } from "@/types";

// ── Colour palette for hospital nodes (cycles if more hospitals than colours) ─
const NODE_COLORS = [
  "var(--accent)",      // UGMC (Teal)
  "var(--gold)",        // KATH (Gold)
  "#805AD5",            // Purple
  "var(--ok)",          // Green
  "var(--danger)",      // Red
  "#319795",            // Cyan/Teal
  "#DD6B20",            // Orange
  "var(--muted)",       // Slate
];

/**
 * Arrange n hospitals evenly around a circle in the SVG viewport (800 × 480).
 * Returns a map of hospital.id → { cx, cy, color }.
 */
function computePositions(
  hospitals: Hospital[]
): Record<number, { cx: number; cy: number; color: string }> {
  const n = hospitals.length;
  if (n === 0) return {};
  // Centre of the SVG viewport
  const CX = 400, CY = 240;
  // Radius: shrinks for a single hospital, capped at 160 for clarity
  const R = n === 1 ? 0 : Math.min(160, 400 / n + 80);
  return Object.fromEntries(
    hospitals.map((h, i) => {
      // Start at the top (−π/2) and go clockwise
      const angle = n === 1 ? 0 : (2 * Math.PI * i) / n - Math.PI / 2;
      return [
        h.id,
        {
          cx: Math.round(CX + R * Math.cos(angle)),
          cy: Math.round(CY + R * Math.sin(angle)),
          color: NODE_COLORS[i % NODE_COLORS.length],
        },
      ];
    })
  );
}

/** Count referrals between two hospitals by their database IDs. */
function countReferrals(referrals: Referral[], fromId: number, toId: number): number {
  return referrals.filter(
    (r) => r.from_hospital === fromId && r.to_hospital === toId
  ).length;
}

interface NodePopoverProps {
  hospital: Hospital;
  referralCount: number;
}

function NodePopover({ hospital, referralCount }: NodePopoverProps) {
  return (
    <Card withBorder radius="md" p="sm" maw={240}>
      <Text fw={700} size="sm">{hospital.name}</Text>
      <Text size="xs" c="dimmed" mb="xs">{hospital.city}</Text>
      <Group gap="xs">
        <Badge size="xs" color={hospital.is_active ? "green" : "red"} variant="light">
          {hospital.is_active ? "Active" : "Inactive"}
        </Badge>
        <Badge size="xs" color="blue" variant="light">{referralCount} referrals</Badge>
      </Group>
    </Card>
  );
}

export function NetworkMapPage() {
  const [openNode, setOpenNode] = useState<number | null>(null);

  const { data: hospitalsData, isLoading: loadingH } = useQuery({
    queryKey: ["hospitals"],
    queryFn: () => fetchHospitals().then((r) => r.data),
  });

  const { data: referrals = [], isLoading: loadingR, refetch } = useQuery({
    queryKey: ["referrals-network"],
    queryFn: () => fetchReferrals().then((r) => r.data.results ?? []),
    staleTime: 30_000,
  });

  const hospitals = (hospitalsData?.results ?? []) as Hospital[];
  const positions = computePositions(hospitals);

  // Generate all ordered pairs (A→B and B→A) for every hospital combination
  const edges: [Hospital, Hospital][] = [];
  for (let i = 0; i < hospitals.length; i++) {
    for (let j = i + 1; j < hospitals.length; j++) {
      edges.push([hospitals[i], hospitals[j]]);
      edges.push([hospitals[j], hospitals[i]]);
    }
  }

  if (loadingH || loadingR) {
    return (
      <Stack gap="md">
        <Skeleton height={60} />
        <Skeleton height={480} radius="lg" />
      </Stack>
    );
  }

  if (hospitals.length === 0) {
    return (
      <Stack gap="lg">
        <Text c="dimmed" ta="center" py="xl">
          No hospitals found. Add hospitals first to see the referral network.
        </Text>
      </Stack>
    );
  }

  const openHospital = hospitals.find((h) => h.id === openNode) ?? null;

  return (
    <Stack gap="lg">
      <Group justify="space-between">
        <Group gap="xs">
          <ThemeIcon size={36} color="medsync" variant="light" radius="md">
            <IconArrowLeftRight size={20} />
          </ThemeIcon>
          <Box>
            <Title order={2}>Referral Network Map</Title>
            <Text size="xs" c="dimmed">
              Live inter-hospital referral flow · {hospitals.length} hospital{hospitals.length !== 1 ? "s" : ""}
            </Text>
          </Box>
        </Group>
        <Button leftSection={<IconRefresh size={16} />} variant="subtle" size="sm" onClick={() => refetch()}>
          Refresh
        </Button>
      </Group>

      {/* SVG Network Diagram */}
      <Card withBorder radius="lg" p={0} style={{ overflow: "hidden", position: "relative", borderColor: "var(--line)" }}>
        <Box
          style={{
            background: "linear-gradient(135deg, var(--ink) 0%, var(--mist) 100%)",
            padding: "1rem",
          }}
        >
          <svg viewBox="0 0 800 480" style={{ width: "100%", height: "auto", maxHeight: 480 }}>
            <defs>
              {/* Arrow marker */}
              <marker id="arrow" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
                <polygon points="0 0, 10 3.5, 0 7" fill="rgba(255,255,255,0.5)" />
              </marker>
              {/* Glow filter */}
              <filter id="glow">
                <feGaussianBlur stdDeviation="3" result="coloredBlur" />
                <feMerge><feMergeNode in="coloredBlur" /><feMergeNode in="SourceGraphic" /></feMerge>
              </filter>
              {/* Animated dash and pulse */}
              <style>{`
                @keyframes dash { to { stroke-dashoffset: -24; } }
                .referral-line { animation: dash 1.5s linear infinite; }
                @keyframes pulseRing {
                  0% { r: 32px; opacity: 0.8; }
                  100% { r: 56px; opacity: 0; }
                }
                .pulse-ring {
                  animation: pulseRing 1.5s cubic-bezier(0.215, 0.61, 0.355, 1) infinite;
                }
              `}</style>
            </defs>

            {/* Edges */}
            {edges.map(([from, to]) => {
              const s = positions[from.id];
              const t = positions[to.id];
              if (!s || !t) return null;
              const count = countReferrals(referrals, from.id, to.id);
              // Perpendicular offset to separate bidirectional edges
              const dx = t.cy - s.cy, dy = s.cx - t.cx;
              const len = Math.sqrt(dx * dx + dy * dy) || 1;
              const ox = (dx / len) * 10, oy = (dy / len) * 10;
              const x1 = s.cx + ox, y1 = s.cy + oy;
              const x2 = t.cx + ox, y2 = t.cy + oy;

              // Highlighting logic
              const isRelated = openNode === null || from.id === openNode || to.id === openNode;
              const baseOpacity = isRelated ? (count > 0 ? 0.85 : 0.2) : 0.04;
              const strokeW = (count > 5 ? 3 : count > 2 ? 2 : 1.5) * (isRelated && openNode !== null ? 1.5 : 1);
              const animSpeed = isRelated && openNode !== null ? "0.7s" : "1.5s";

              return (
                <g key={`${from.id}-${to.id}`} style={{ transition: "opacity 0.25s ease" }}>
                  <line
                    x1={x1} y1={y1} x2={x2} y2={y2}
                    stroke="rgba(255,255,255,0.08)"
                    strokeWidth={strokeW + 2}
                    style={{ opacity: isRelated ? 1.0 : 0.1 }}
                  />
                  <line
                    className="referral-line"
                    x1={x1} y1={y1} x2={x2} y2={y2}
                    stroke={`rgba(255,255,255,${baseOpacity})`}
                    strokeWidth={strokeW}
                    strokeDasharray="12 12"
                    markerEnd="url(#arrow)"
                    style={{ animationDuration: animSpeed }}
                  />
                  {count > 0 && isRelated && (
                    <text
                      x={(x1 + x2) / 2 + ox * 0.5}
                      y={(y1 + y2) / 2 + oy * 0.5}
                      fill="white"
                      fontSize="13"
                      fontWeight="bold"
                      textAnchor="middle"
                      dominantBaseline="middle"
                      filter="url(#glow)"
                      style={{ opacity: openNode === null ? 1.0 : (from.id === openNode || to.id === openNode ? 1.0 : 0.2) }}
                    >
                      {count}
                    </text>
                  )}
                </g>
              );
            })}

            {/* Nodes */}
            {hospitals.map((hosp) => {
              const pos = positions[hosp.id];
              if (!pos) return null;
              
              const isActive = hosp.id === openNode;
              const isDimmed = openNode !== null && !isActive;
              
              const totalRx = referrals.filter(
                (r: Referral) => r.from_hospital === hosp.id || r.to_hospital === hosp.id
              ).length;
              
              return (
                <g
                  key={hosp.id}
                  onClick={() => setOpenNode(openNode === hosp.id ? null : hosp.id)}
                  style={{
                    cursor: "pointer",
                    opacity: isDimmed ? 0.3 : 1.0,
                    transition: "opacity 0.25s ease"
                  }}
                >
                  {/* Outer glow rings */}
                  <circle cx={pos.cx} cy={pos.cy} r={46} fill={pos.color} opacity={0.12} />
                  <circle cx={pos.cx} cy={pos.cy} r={38} fill={pos.color} opacity={0.22} />
                  {/* Selected pulsing ring */}
                  {isActive && (
                    <circle
                      cx={pos.cx}
                      cy={pos.cy}
                      r={32}
                      fill="none"
                      stroke={pos.color}
                      strokeWidth={2}
                      className="pulse-ring"
                    />
                  )}
                  {/* Main node */}
                  <circle cx={pos.cx} cy={pos.cy} r={32} fill={pos.color} filter="url(#glow)" />
                  {/* Hospital code label */}
                  <text
                    x={pos.cx} y={pos.cy - 4}
                    fill="white" fontSize="12" fontWeight="bold"
                    textAnchor="middle" dominantBaseline="middle"
                  >
                    {hosp.code}
                  </text>
                  <text
                    x={pos.cx} y={pos.cy + 11}
                    fill="rgba(255,255,255,0.8)" fontSize="9"
                    textAnchor="middle"
                  >
                    {totalRx} referrals
                  </text>
                  {/* City label below node */}
                  <text
                    x={pos.cx} y={pos.cy + 54}
                    fill="rgba(255,255,255,0.7)" fontSize="11"
                    textAnchor="middle"
                  >
                    {hosp.city ?? hosp.code}
                  </text>
                </g>
              );
            })}
          </svg>
        </Box>

        {/* Click-node popover (rendered outside SVG as overlay) */}
        {openHospital && (
          <Box
            style={{
              position: "absolute",
              top: "1rem",
              right: "1rem",
            }}
          >
            <NodePopover
              hospital={openHospital}
              referralCount={referrals.filter(
                (r: Referral) => r.from_hospital === openHospital.id || r.to_hospital === openHospital.id
              ).length}
            />
            <Button size="xs" variant="subtle" fullWidth mt={4} onClick={() => setOpenNode(null)}>
              Close
            </Button>
          </Box>
        )}
      </Card>

      {/* Summary cards — one per hospital */}
      <SimpleGrid cols={{ base: 1, sm: Math.min(hospitals.length, 3) }} spacing="md">
        {hospitals.map((hosp) => {
          const pos = positions[hosp.id];
          const sent     = referrals.filter((r: Referral) => r.from_hospital === hosp.id).length;
          const received = referrals.filter((r: Referral) => r.to_hospital   === hosp.id).length;
          return (
            <Card
              key={hosp.id}
              withBorder
              radius="md"
              p="md"
              style={{ borderLeftWidth: 3, borderLeftColor: pos?.color ?? "#228be6" }}
            >
              <Group gap="xs" mb="xs">
                <ThemeIcon
                  size={32}
                  radius="md"
                  variant="light"
                  style={{ background: (pos?.color ?? "#228be6") + "22" }}
                >
                  <IconBuilding size={18} style={{ color: pos?.color ?? "#228be6" }} />
                </ThemeIcon>
                <Box>
                  <Text fw={700} size="sm">{hosp.code}</Text>
                  <Text size="xs" c="dimmed">{hosp.city}</Text>
                </Box>
              </Group>
              <Group gap="sm">
                <Box><Text size="xs" c="dimmed">Sent</Text><Text fw={700}>{sent}</Text></Box>
                <Box><Text size="xs" c="dimmed">Received</Text><Text fw={700}>{received}</Text></Box>
                <Box><Text size="xs" c="dimmed">Total</Text><Text fw={700}>{sent + received}</Text></Box>
              </Group>
            </Card>
          );
        })}
      </SimpleGrid>
    </Stack>
  );
}
