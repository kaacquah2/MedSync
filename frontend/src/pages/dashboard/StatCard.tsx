import { Link } from "react-router-dom";
import type { StatCard as StatCardType } from "@/types";

interface Props {
  stat: StatCardType;
}

const COLOR_CLASS_MAP: Record<string, string> = {
  primary: "blue",
  success: "green",
  info: "blue",
  warning: "amber",
  danger: "red",
  secondary: "amber",
  blue: "blue",
  green: "green",
  amber: "amber",
  red: "red",
};

export function StatCard({ stat }: Props) {
  const colorClass = COLOR_CLASS_MAP[stat.color] ?? "blue";
  
  // Custom delta text based on the label, or fallback to the provided stat.delta
  let deltaText = stat.delta || "";
  let deltaColorClass = "neutral";
  
  if (deltaText.includes("+") || deltaText.includes("↑")) {
    deltaColorClass = "up";
  } else if (deltaText.includes("-") || deltaText.includes("↓")) {
    deltaColorClass = "down";
  }

  const cardContent = (
    <>
      <div className="label">{stat.label}</div>
      <div className="value">{stat.value}</div>
      {deltaText && (
        <div className={`delta ${deltaColorClass}`}>
          {deltaText}
        </div>
      )}
    </>
  );

  const className = `stat-card ${colorClass}`;

  if (stat.link) {
    return (
      <Link to={stat.link} className={className}>
        {cardContent}
      </Link>
    );
  }

  return (
    <div className={className}>
      {cardContent}
    </div>
  );
}
