import React from "react";
import { Badge, Tooltip } from "@mantine/core";
import { IconLock, IconShieldLock } from "@tabler/icons-react";
import { ConfidentialityLevel } from "@/types";

interface ConfidentialityBadgeProps {
  level?: ConfidentialityLevel | string | null;
  size?: "xs" | "sm" | "md";
  showNormal?: boolean;
}

export const ConfidentialityBadge: React.FC<ConfidentialityBadgeProps> = ({
  level,
  size = "xs",
  showNormal = false,
}) => {
  if (!level || level === "normal") {
    if (!showNormal) return null;
    return (
      <Badge color="gray" variant="outline" size={size}>
        Standard
      </Badge>
    );
  }

  if (level === "restricted") {
    return (
      <Tooltip
        label="Restricted Record: Protected health data under Ghana Act 843 §37 & ISO 22600"
        withArrow
      >
        <Badge
          color="grape"
          variant="filled"
          size={size}
          leftSection={<IconShieldLock size={size === "xs" ? 11 : 13} />}
          style={{ textTransform: "none", fontWeight: 600 }}
        >
          Restricted
        </Badge>
      </Tooltip>
    );
  }

  if (level === "very_restricted") {
    return (
      <Tooltip
        label="Very Restricted: Highly sensitive / VIP record under strict statutory confidentiality"
        withArrow
      >
        <Badge
          color="red"
          variant="filled"
          size={size}
          leftSection={<IconLock size={size === "xs" ? 11 : 13} />}
          style={{ textTransform: "none", fontWeight: 700, letterSpacing: "0.02em" }}
        >
          Very Restricted
        </Badge>
      </Tooltip>
    );
  }

  return null;
};
