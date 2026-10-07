import { $, compact, dayKey } from './types.js';
export function acceptsAdditional(info, selected) {
    return info.symbol === selected.symbol && info.request_id === selected.request_id &&
        info.mode === selected.mode && info.source === selected.source;
}
export function marketCap(value) {
    const number = value == null ? NaN : Number(value);
    return Number.isFinite(number) && number > 0 ? compact(number) : '';
}
export function categoryText(sector, industry) {
    const labels = [sector, industry].map(value => (value ?? '').split(':', 1)[0]
        .replace(/\([^)]*\)/g, '').replace(/\s+/g, ' ').trim()).filter(Boolean);
    return labels.filter((label, index) => index === 0 || label.toLowerCase() !== labels[0].toLowerCase()).join(' · ');
}
const dayNumber = (day) => Date.parse(day + 'T00:00:00Z') / 86400000;
export function earningsText(info, now = info.server_time) {
    const today = dayNumber(dayKey(now));
    const last = info.earnings.last, next = info.earnings.next;
    const ago = last ? today - dayNumber(last.date) : Infinity;
    const until = next ? dayNumber(next.date) - today : -1;
    const recent = last && ago >= 0 && (ago <= 7 || until < 0);
    const event = recent ? last : until >= 0 ? next : null;
    if (!event)
        return { text: '', title: '', label: '', countdown: '' };
    const days = recent ? ago : until, units = days === 1 ? 'day' : 'days';
    const label = recent ? 'Last earnings report' : days === 0 ? 'Earnings today' : 'Next earnings report';
    const countdown = recent ? days === 0 ? 'Today' : `${days} ${units} ago` : days === 0 ? '' : `In ${days} ${units}`;
    const text = [label, countdown].filter(Boolean).join(' · ');
    const session = { 'time-pre-market': 'Pre-market', 'time-after-hours': 'After hours' }[event.session ?? ''];
    const title = [recent ? 'Reported earnings' : 'Estimated earnings date', event.date, session,
        event.fiscal_period ? 'Fiscal quarter ending ' + event.fiscal_period : '',
        info.earnings_updated_at ? 'Updated ' + info.earnings_updated_at : ''].filter(Boolean).join(' · ');
    return { text, title, label, countdown };
}
export class AdditionalInfoDisplay {
    value = null;
    offset = 0;
    update(info) {
        this.value = info;
        this.offset = info ? info.server_time * 1000 - Date.now() : 0;
        const name = info?.company_name ?? '';
        const company = $('daily-company-name');
        company.textContent = name;
        company.title = [name, info?.companies_updated_at ? 'Updated ' + info.companies_updated_at : ''].filter(Boolean).join(' · ');
        company.hidden = !name;
        const category = categoryText(info?.sector ?? null, info?.industry ?? null);
        const classification = $('daily-classification');
        classification.textContent = classification.title = category;
        classification.hidden = !category;
        const cap = marketCap(info?.market_cap ?? null), node = $('intraday-market-cap');
        node.textContent = cap ? 'Market Cap ' + cap : '';
        node.title = cap ? 'Market Cap $' + Number(info.market_cap).toLocaleString('en-US') +
            (info?.companies_updated_at ? ' · Updated ' + info.companies_updated_at : '') : '';
        node.hidden = !cap;
        this.tick();
    }
    tick() {
        const label = this.value ? earningsText(this.value, (Date.now() + this.offset) / 1000) : { text: '', title: '', label: '', countdown: '' };
        const node = $('daily-earnings');
        $('daily-earnings-label').textContent = label.label;
        $('daily-earnings-countdown').textContent = label.countdown ? '· ' + label.countdown : '';
        node.setAttribute('aria-label', label.text);
        node.title = label.title;
        node.hidden = !label.text;
    }
}
