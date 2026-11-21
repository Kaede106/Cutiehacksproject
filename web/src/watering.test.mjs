import assert from 'node:assert/strict';
import { test } from 'node:test';
import { cadenceForDemand, estimateWeeklyEt0, simulateWatering } from './watering.js';

// Reference values from farm.bot.irrigation: _hargreaves_week with three air
// readings over 12 hours and one fresh soil reading, then advise with that
// weekly ET0 and the rain total supplied as seven WeatherDay entries.
const defaults = { soil: 48, low: 17, high: 34, humidity: 45, wind: 2, rain: 0 };
const summer = '2026-06-22';
const summerEt0 = 48.72782283953153;
const cases = [
  ['summer default', {}, summer, summerEt0, 'twice a week', '2026-06-25', 31.7],
  ['moisture at the threshold', { soil: 35, rain: 10 }, summer, summerEt0, 'weekly', '2026-06-29', 21.7],
  ['two weeks after rain', { rain: 23 }, summer, summerEt0, 'every 2 weeks', '2026-07-06', 8.7],
  ['rain exceeds citrus need', { rain: 40 }, summer, summerEt0, 'hold off', null, 0],
  ['dry soil overrides rain', { soil: 34, rain: 60 }, summer, summerEt0, 'water today', summer, null],
  ['dry and windy', { humidity: 39, wind: 4, rain: 12 }, summer, 58.96066563583316, 'twice a week', '2026-06-25', 26.3],
  ['just inside neutral air', { humidity: 40, wind: 3.5, rain: 12 }, summer, summerEt0, 'weekly', '2026-06-29', 19.7],
  ['humidity at 70%', { humidity: 70, rain: 3 }, summer, summerEt0, 'twice a week', '2026-06-25', 28.7],
  ['humidity above 70%', { humidity: 71, rain: 3 }, summer, 43.85504055557838, 'twice a week', '2026-06-25', 25.5],
  ['leap day with reversed temperatures', { low: 8, high: -5 }, '2028-02-29', 12.217264389742429, 'every 2 weeks', '2028-03-14', 7.9],
  ['equal temperatures', { low: 25, high: 25 }, summer, 0, 'hold off', null, 0],
];

for (const [name, overrides, day, et0, cadence, nextDue, demand] of cases) {
  test(name, () => {
    const inputs = { ...defaults, ...overrides };
    const today = new Date(day);
    assert.ok(Math.abs(estimateWeeklyEt0(inputs, today) - et0) < 1e-10);
    const advice = simulateWatering(inputs, today);
    assert.equal(advice.cadence, cadence);
    assert.equal(advice.nextDue?.toISOString().slice(0, 10) ?? null, nextDue);
    assert.equal(advice.demandMm === null ? null : Number(advice.demandMm.toFixed(1)), demand);
  });
}

test('demand cutoffs match the bot at and just below each boundary', () => {
  assert.deepEqual(
    [4.999, 5, 11.999, 12, 24.999, 25].map(cadenceForDemand),
    ['hold off', 'every 2 weeks', 'every 2 weeks', 'weekly', 'weekly', 'twice a week'],
  );
});
