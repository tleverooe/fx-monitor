'use strict';

const byId = id => document.getElementById(id);
const timestamp = new Intl.DateTimeFormat('zh-CN', {
  timeZone: 'Asia/Shanghai', dateStyle: 'short', timeStyle: 'medium',
});
const beijingDate = new Intl.DateTimeFormat('sv-SE', {
  timeZone: 'Asia/Shanghai', dateStyle: 'short',
});
const dayMs = 86_400_000;
const display = value => Number(value).toFixed(value < 0.1 ? 6 : 4);
let data;
let days = 0;
let dayOffset = 0;

function chart(rows, minimum, maximum) {
  const canvas = byId('chart');
  const {width, height} = canvas.getBoundingClientRect();
  const density = window.devicePixelRatio || 1;
  canvas.width = Math.round(width * density);
  canvas.height = Math.round(height * density);
  const context = canvas.getContext('2d');
  context.scale(density, density);
  context.font = '12px system-ui';
  context.fillStyle = '#476267';
  if (!rows.length) {
    context.textAlign = 'center';
    context.fillText('该时段暂无采集数据', width / 2, height / 2);
    return;
  }
  const left = 70;
  const right = width - 10;
  const top = 14;
  const bottom = height - 26;
  const padding = minimum === maximum ? minimum * .001 : 0;
  const high = maximum + padding;
  const low = minimum - padding;
  const start = Date.parse(rows[0].t);
  const end = Date.parse(rows.at(-1).t);
  const x = row => end === start ? (left + right) / 2
    : left + (right - left) * (Date.parse(row.t) - start) / (end - start);
  const y = row => top + (bottom - top) * (high - row.v) / (high - low);
  for (let index = 0; index <= 4; index++) {
    const line = top + (bottom - top) * index / 4;
    context.strokeStyle = '#d7e4de';
    context.beginPath();
    context.moveTo(left, line);
    context.lineTo(right, line);
    context.stroke();
    context.textAlign = 'right';
    context.fillText(display(high - (high - low) * index / 4), left - 6, line + 4);
  }
  context.strokeStyle = '#145a4c';
  context.lineWidth = 2;
  context.beginPath();
  let previous;
  for (const row of rows) {
    if (!previous || Date.parse(row.t) - Date.parse(previous.t) > 3_600_000) {
      if (previous) {
        context.moveTo(x(previous), y(previous));
        context.arc(x(previous), y(previous), 2, 0, 2 * Math.PI);
      }
      context.moveTo(x(row), y(row));
    } else {
      context.lineTo(x(row), y(row));
    }
    previous = row;
  }
  context.stroke();
  context.beginPath();
  context.arc(x(previous), y(previous), 3, 0, 2 * Math.PI);
  context.fillStyle = '#145a4c';
  context.fill();
  const label = row => row.t.slice(5, 16).replace('T', ' ');
  context.textAlign = 'left';
  context.fillText(label(rows[0]), left, height - 7);
  if (start !== end) {
    context.textAlign = 'right';
    context.fillText(label(previous), right, height - 7);
  }
}

function calculate() {
  const code = byId('currency').value;
  const input = byId('amount');
  const value = data?.series[code]?.at(-1)?.v;
  const cost = input.valueAsNumber * value;
  byId('cost').textContent = Number.isFinite(cost) && input.validity.valid
    ? new Intl.NumberFormat('zh-CN', {style: 'currency', currency: 'CNY'}).format(cost)
    : '—';
}

function render() {
  if (!data) return;
  const code = byId('currency').value;
  const all = data.series[code] || [];
  const last = all.at(-1);
  const now = Date.now();
  const today = beijingDate.format(now);
  const selectedDate = dayOffset ? beijingDate.format(now - dayMs) : today;
  dayNavigation.hidden = days !== 0;
  dayLabel.textContent = (dayOffset ? '昨日 ' : '今日 ') + selectedDate;
  previousDay.disabled = dayOffset === 1;
  nextDay.disabled = dayOffset === 0;
  byId('chart').setAttribute('aria-label', days
    ? '近 ' + days + ' 天购汇价格走势图' : dayLabel.textContent + '购汇价格走势图');
  const rows = days
    ? all.filter(row => Date.parse(row.t) >= now - days * dayMs)
    : all.filter(row => row.t.startsWith(selectedDate));
  byId('price').textContent = last ? '¥' + display(last.v) : '暂无报价';
  byId('unit').textContent = '人民币 / 1 ' + code;
  byId('amount-unit').textContent = '（' + code + '）';
  byId('target').textContent = code === data.monitor_currency
    ? '提醒目标 ¥' + data.target_price : '';
  byId('stamp').textContent = last ? '银行报价 ' + timestamp.format(new Date(last.t))
    + (now - Date.parse(last.t) > 7_200_000 ? '（超过两小时）' : '') : '等待首次采集';
  byId('status').textContent = data.checked_at
    ? '最近一次成功采集 ' + timestamp.format(new Date(data.checked_at))
      + (now - Date.parse(data.checked_at) > 1_800_000 ? '（采集延迟）' : '')
    : '尚未采集';
  let minimum = Infinity;
  let maximum = -Infinity;
  for (const row of rows) {
    minimum = Math.min(minimum, row.v);
    maximum = Math.max(maximum, row.v);
  }
  byId('min').textContent = rows.length ? display(minimum) : '—';
  byId('max').textContent = rows.length ? display(maximum) : '—';
  const count = data.coverage?.[code]?.[days];
  byId('coverage').textContent = count === undefined
    ? '仅展示已采集的报价。所有时间为北京时间。'
    : '五分钟采集覆盖 ' + count + '/' + days * 288
      + (count === days * 288 ? '（完整）' : '（历史不完整）')
      + '。所有时间为北京时间。';
  chart(rows, minimum, maximum);
  calculate();
}

async function reload() {
  try {
    const response = await fetch('rates.json', {cache: 'no-store'});
    if (!response.ok) throw new Error('HTTP ' + response.status);
    data = await response.json();
    const select = byId('currency');
    const selected = select.value || data.monitor_currency || 'AUD';
    select.replaceChildren(...Object.entries(data.currencies).map(
      ([code, name]) => new Option(name + ' ' + code, code)));
    if (selected in data.currencies) select.value = selected;
    render();
  } catch {
    byId('status').textContent = '刷新失败，请稍后重试。';
  }
}

for (const period of [0, 7, 30, 90]) {
  const button = document.createElement('button');
  button.textContent = period ? period + ' 天' : '单天';
  button.setAttribute('aria-pressed', String(period === days));
  button.addEventListener('click', () => {
    days = period;
    dayOffset = 0;
    for (const entry of byId('periods').children) {
      entry.setAttribute('aria-pressed', String(entry === button));
    }
    render();
  });
  byId('periods').append(button);
}
const dayNavigation = document.createElement('div');
dayNavigation.hidden = true;
const dayControls = document.createElement('div');
dayControls.className = 'day-controls';
dayControls.setAttribute('role', 'group');
dayControls.setAttribute('aria-label', '按日查看走势');
const dayLabel = document.createElement('span');
dayLabel.setAttribute('aria-live', 'polite');

function createDayButton(symbol, label, offset) {
  const button = document.createElement('button');
  button.type = 'button';
  button.textContent = symbol;
  button.setAttribute('aria-label', label);
  button.addEventListener('click', () => {
    dayOffset = offset;
    render();
    (offset ? nextDay : previousDay).focus();
  });
  return button;
}

const previousDay = createDayButton('←', '查看昨日走势', 1);
const nextDay = createDayButton('→', '返回今日走势', 0);
dayControls.append(previousDay, dayLabel, nextDay);
dayNavigation.append(dayControls);
byId('periods').after(dayNavigation);

byId('currency').addEventListener('change', render);
byId('amount').addEventListener('input', calculate);
byId('refresh').addEventListener('click', reload);
window.addEventListener('resize', render);
reload();
setInterval(reload, 60_000);
