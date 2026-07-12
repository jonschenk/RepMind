import { createContext, ReactNode, useContext, useEffect, useState } from "react";

// Weights are stored/sent to Hevy in kilograms everywhere. This is a DISPLAY unit only:
// convert kg -> the user's unit on the way out, and back to kg when they edit a value.
const KG_TO_LB = 2.2046;
export type Unit = "lb" | "kg";

interface UnitCtx {
  unit: Unit;
  setUnit: (u: Unit) => void;
}
const Ctx = createContext<UnitCtx>({ unit: "lb", setUnit: () => {} });

export function UnitProvider({ children }: { children: ReactNode }) {
  const [unit, setUnitState] = useState<Unit>(
    () => ((localStorage.getItem("weight_unit") as Unit) || "lb"),
  );

  // Server preference is the source of truth (persists across devices); localStorage
  // gives an instant default before it loads.
  useEffect(() => {
    fetch("/api/settings")
      .then((r) => r.json())
      .then((d) => {
        if (d.weight_unit === "lb" || d.weight_unit === "kg") {
          setUnitState(d.weight_unit);
          localStorage.setItem("weight_unit", d.weight_unit);
        }
      })
      .catch(() => {});
  }, []);

  function setUnit(u: Unit) {
    setUnitState(u);
    localStorage.setItem("weight_unit", u);
    fetch("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ weight_unit: u }),
    }).catch(() => {});
  }

  return <Ctx.Provider value={{ unit, setUnit }}>{children}</Ctx.Provider>;
}

export const useUnit = () => useContext(Ctx);

export const toUnit = (kg: number, unit: Unit): number => (unit === "lb" ? kg * KG_TO_LB : kg);
export const fromUnit = (val: number, unit: Unit): number => (unit === "lb" ? val / KG_TO_LB : val);
export const round1 = (n: number): number => Math.round(n * 10) / 10;

export function fmtWeight(kg: number | null | undefined, unit: Unit): string {
  if (kg == null) return "-";
  return `${round1(toUnit(kg, unit))} ${unit}`;
}
