// RunKPIs.tsx
import * as React from "react";
import {
  Box, Card, Typography, Stack, Chip, LinearProgress, CircularProgress,
} from "@mui/material";
// Grid v2
import Grid from "@mui/material/Grid";
import { alpha, keyframes } from "@mui/material/styles";
import type { TestResult } from "../../api/models";

type Props = {
  /** Vollständige Ergebnisliste aus der RunDetailPage */
  results: TestResult[];
  /** Optional: Zielwert für Anzahl Ergebnisse (zeigt Mini-Progress) */
  resultsGoal?: number;
  /** Optional: Maximal möglicher PQS (Default 5^5 = 3125) */
  pqsMax?: number;
};

const shimmer = keyframes`
  0% { background-position: 0% 50%; }
  100% { background-position: 200% 50%; }
`;

function Ring({ value, size = 84 }: { value: number; size?: number }) {
  return (
    <Box sx={{ position: "relative", display: "inline-flex" }}>
      <CircularProgress variant="determinate" value={100}
        sx={{ color: (t) => alpha(t.palette.text.primary, 0.1) }}
        size={size} thickness={5}/>
      <CircularProgress variant="determinate" value={value}
        sx={{ position: "absolute", left: 0 }} size={size} thickness={5}/>
      <Box sx={{
        position: "absolute", inset: 0, display: "flex",
        alignItems: "center", justifyContent: "center"
      }}>
        <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
          {Math.round(value)}%
        </Typography>
      </Box>
    </Box>
  );
}

function Meter({ pct }: { pct: number }) {
  return (
    <Stack spacing={0.75}>
      <LinearProgress variant="determinate" value={pct}
        sx={{
          height: 8, borderRadius: 6,
          backgroundColor: (t) => alpha(t.palette.text.primary, 0.08),
        }}
      />
      <Box sx={{ display: "flex", justifyContent: "space-between", gap: 1 }}>
        {[0, 25, 50, 75, 100].map((m) => (
          <Box key={m} sx={{
            flex: 1, height: 6, borderRadius: 1,
            backgroundColor: (t) => alpha(t.palette.text.primary, 0.3),
          }}/>
        ))}
      </Box>
    </Stack>
  );
}

const CardWrap: React.FC<React.PropsWithChildren<{title: string; subtitle?: string; badge?: string;}>> =
({ title, subtitle, badge, children }) => (
  <Card
    sx={{
      p: 2.25, height: "100%", borderRadius: 3, position: "relative",
      border: "1px solid transparent",
      background:
        `linear-gradient(${alpha("#fff", 1)}, ${alpha("#fff", 1)}) padding-box,` +
        `linear-gradient(90deg, rgba(99,102,241,.35), rgba(16,185,129,.35), rgba(245,158,11,.35)) border-box`,
      backgroundSize: "200% 100%", animation: `${shimmer} 12s linear infinite`,
    }}
    elevation={0}
  >
    <Stack spacing={1.25}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
        <Typography variant="overline" sx={{ letterSpacing: 1.1, opacity: 0.8 }}>
          {title}
        </Typography>
        {badge && <Chip size="small" label={badge} />}
      </Box>
      {children}
      {subtitle && (
        <Typography variant="caption" sx={{ opacity: 0.7 }}>
          {subtitle}
        </Typography>
      )}
    </Stack>
  </Card>
);

/** Holt die fünf Scores aus TestResult */
function extractFiveScores(r: TestResult): (number | undefined)[] {
  const rel = r.relevance;
  const fak = r.factual_accuracy;
  const vst = r.completeness;
  const ton = r.tone;
  const vstl = r.comprehensibility;
  return [rel, fak, vst, ton, vstl];
}

/** Produkt (PQS raw) nur berechnen, wenn alle 5 vorhanden sind */
function productIfComplete(vals: (number | undefined)[]) {
  if (vals.some((v) => typeof v !== "number")) return undefined;
  return (vals as number[]).reduce((a, b) => a * b, 1);
}

export default function RunKPIs({
  results,
  resultsGoal,
  pqsMax = 3125, // 5^5
}: Props) {
  const count = results?.length ?? 0;

  // Alle Scores einsammeln
  const perResultScores = React.useMemo(() => results.map(extractFiveScores), [results]);

  // Ø Subscore über alle vorhandenen Einzelwerte
  const allSingles = React.useMemo(
    () => perResultScores.flat().filter((v): v is number => typeof v === "number" && Number.isFinite(v)),
    [perResultScores]
  );
  const subAvg = allSingles.length
    ? allSingles.reduce((a, b) => a + b, 0) / allSingles.length
    : 0;

  // PQS raw: Mittelwert der vollständigen Produkte (nur Ergebnisse mit 5 Werten)
  const products = React.useMemo(
    () => perResultScores
      .map(productIfComplete)
      .filter((v): v is number => typeof v === "number" && Number.isFinite(v)),
    [perResultScores]
  );
  const pqsRaw = products.length
    ? products.reduce((a, b) => a + b, 0) / products.length
    : 0;

  // Visualisierungen
  const clamp = (n: number, lo = 0, hi = 100) => Math.max(lo, Math.min(hi, n));
  const pqsPct = clamp((pqsRaw / pqsMax) * 100);
  const subPct = clamp((subAvg / 5) * 100);
  const subLabel =
    subAvg >= 4.5 ? "Outstanding" :
    subAvg >= 4.0 ? "Strong" :
    subAvg >= 3.0 ? "Okay" : "Low";

  const resPct = typeof resultsGoal === "number" && resultsGoal > 0
    ? clamp((count / resultsGoal) * 100)
    : undefined;

  return (
    <Grid container spacing={2.25} sx={{ width: "100%", mb: 2 }}>
      {/* PQS Hero */}
      <Grid size={{ xs: 12, md: 4 }}>
        <CardWrap
          title="PQS Ø (RAW)"
          subtitle={`Produkt der 5 Kategorien (1–${pqsMax.toLocaleString("de-DE")})`}
          badge={`${Math.round(pqsPct)}. Perzentil`}
        >
          <Stack direction="row" alignItems="center" spacing={2}>
            <Ring value={pqsPct}/>
            <Box>
              <Typography variant="h4" sx={{ fontWeight: 800, lineHeight: 1 }}>
                {pqsRaw.toLocaleString("de-DE")}
              </Typography>
              <Typography variant="body2" sx={{ opacity: 0.75 }}>
                relativ zu Max-Score
              </Typography>
            </Box>
          </Stack>
        </CardWrap>
      </Grid>

      {/* Ø Subscore */}
      <Grid size={{ xs: 12, md: 4 }}>
        <CardWrap title="Ø SUBSCORE" subtitle="Skala 0–5" badge={subLabel}>
          <Stack spacing={1}>
            <Typography variant="h4" sx={{ fontWeight: 800, lineHeight: 1 }}>
              {subAvg.toFixed(2).replace(".", ",")}
            </Typography>
            <Meter pct={subPct}/>
          </Stack>
        </CardWrap>
      </Grid>

      {/* Ergebnisse */}
      <Grid size={{ xs: 12, md: 4 }}>
        <CardWrap title="ERGEBNISSE" subtitle="Anzahl ausgewerteter Prompts">
          <Stack spacing={1}>
            <Typography variant="h4" sx={{ fontWeight: 800, lineHeight: 1 }}>
              {count}
            </Typography>
            {typeof resPct === "number" && (
              <Stack spacing={0.5}>
                <LinearProgress variant="determinate" value={resPct}
                  sx={{ height: 8, borderRadius: 6 }}/>
                <Typography variant="caption" sx={{ opacity: 0.7 }}>
                  {Math.round(resPct)}% von Ziel ({resultsGoal})
                </Typography>
              </Stack>
            )}
          </Stack>
        </CardWrap>
      </Grid>
    </Grid>
  );
}
