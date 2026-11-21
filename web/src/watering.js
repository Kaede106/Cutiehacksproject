// Defaults and equations from farm/bot/irrigation.py and farm/bot/.env.example.
const SOIL_THRESHOLD = 35;
const CITRUS_KC = 0.65;
const ASSUMED_LATITUDE = 34;
const DAY_MS = 86_400_000;
const INTERVAL_DAYS = { 'twice a week': 3, weekly: 7, 'every 2 weeks': 14 };

// Dates are UTC calendar days so the example is identical in every time zone.
export function addDays(day, count) {
  return new Date(day.getTime() + count * DAY_MS);
}

export function estimateWeeklyEt0({ low, high, humidity, wind }, day) {
  const yearStart = Date.UTC(day.getUTCFullYear(), 0, 1);
  const dayOfYear = Math.floor((day.getTime() - yearStart) / DAY_MS) + 1;
  const latitude = ASSUMED_LATITUDE * Math.PI / 180;
  const angle = 2 * Math.PI * dayOfYear / 365;
  const distance = 1 + 0.033 * Math.cos(angle);
  const declination = 0.409 * Math.sin(angle - 1.39);
  const sunsetCosine = -Math.tan(latitude) * Math.tan(declination);
  const sunsetAngle = Math.acos(Math.max(-1, Math.min(1, sunsetCosine)));
  const radiation = (24 * 60 / Math.PI) * 0.0820 * distance * (
    sunsetAngle * Math.sin(latitude) * Math.sin(declination) +
    Math.cos(latitude) * Math.cos(declination) * Math.sin(sunsetAngle)
  );
  const mean = (low + high) / 2;
  const dailyEt0 = Math.max(0, 0.0023 * (mean + 17.8) * Math.sqrt(Math.abs(high - low)) * 0.408 * radiation);

  // The bot applies these adjustments to its Hargreaves estimate.
  let airFactor = 1;
  if (humidity < 40) airFactor *= 1.1;
  else if (humidity > 70) airFactor *= 0.9;
  if (wind >= 4) airFactor *= 1.1;
  return dailyEt0 * 7 * airFactor;
}

export function cadenceForDemand(net) {
  if (net < 5) return 'hold off';
  if (net < 12) return 'every 2 weeks';
  if (net < 25) return 'weekly';
  return 'twice a week';
}

export function simulateWatering({ soil, rain, ...air }, today) {
  if (soil < SOIL_THRESHOLD) {
    return {
      cadence: 'water today',
      nextDue: today,
      intervalDays: null,
      demandMm: null,
      reason: `Soil moisture is ${soil}%, below the ${SOIL_THRESHOLD}% threshold.`,
    };
  }

  // Use the sensor-based ET0 estimate with the forecast branch's rain balance.
  const cropNeed = CITRUS_KC * estimateWeeklyEt0(air, today);
  const demandMm = Math.max(cropNeed - rain, 0);
  const cadence = cadenceForDemand(demandMm);
  // One soil reading supplies no drying trend, so use the bot's interval fallback.
  const intervalDays = INTERVAL_DAYS[cadence] ?? null;
  const reason = rain > 0 && demandMm === 0
    ? 'Forecast rain covers this week’s estimated water need.'
    : `Citrus needs about ${demandMm.toFixed(1)} mm ${rain ? 'more after rain ' : ''}this week.`;
  return {
    cadence,
    nextDue: intervalDays === null ? null : addDays(today, intervalDays),
    intervalDays,
    demandMm,
    reason,
  };
}
