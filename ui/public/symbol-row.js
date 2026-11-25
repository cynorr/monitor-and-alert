import { attentionAppearance } from './attention.js';
import { adrText, adrTitle, stateAppearance, volumeBadge } from './intraday-state.js';
export function extendedPercentText(value) {
    if (value == null)
        return '';
    const magnitude = Math.abs(value).toFixed(2);
    return magnitude === '0.00' ? '' : `${value < 0 ? '-' : '+'}${magnitude}%`;
}
export function setListColumns(host, columns, priceEnd) {
    host.style.setProperty('--list-columns', columns.map(({ field, width }) => `[col-${field}] ${width}`).join(' '));
    host.style.setProperty('--price-end', `col-${priceEnd}`);
}
export function listMinimumWidth(grid, content = grid) {
    const viewport = content.parentElement;
    const { marginLeft, marginRight } = getComputedStyle(content);
    grid.style.width = 'min-content';
    const width = grid.getBoundingClientRect().width;
    grid.style.removeProperty('width');
    return Math.ceil(width + parseFloat(marginLeft) + parseFloat(marginRight) + viewport.offsetWidth - viewport.clientWidth);
}
function listCell(field) {
    const cell = document.createElement('div');
    cell.dataset.field = field;
    cell.style.gridColumn = `col-${field}`;
    return cell;
}
export function listCells(row, columns, semantic = false) {
    if (semantic)
        row.setAttribute('role', 'row');
    const cells = {};
    for (const { field } of columns) {
        const cell = listCell(field);
        if (semantic)
            cell.setAttribute('role', 'cell');
        row.append(cell);
        cells[field] = cell;
    }
    return cells;
}
export function listHeader(row, columns, customize) {
    row.replaceChildren(...columns.map(column => {
        const cell = listCell(column.field);
        cell.textContent = column.label;
        customize(cell, column);
        return cell;
    }));
}
export function symbolRow(ticker, columns, priceEnd, semantic = false) {
    const row = document.createElement('div');
    row.className = 'list-grid-row symbol-row';
    row.tabIndex = -1;
    const priceEndIndex = columns.findIndex(column => column.field === priceEnd);
    const cells = listCells(row, columns, semantic);
    for (const { field } of columns.slice(0, priceEndIndex))
        cells[field].classList.add('price-cell');
    const name = document.createElement('button');
    name.className = 'ticker';
    name.type = 'button';
    name.textContent = ticker;
    name.setAttribute('aria-label', `Select ${ticker}`);
    cells.symbol.append(name);
    const surface = document.createElement('span');
    surface.className = 'price-surface';
    surface.setAttribute('aria-hidden', 'true');
    const wave = document.createElement('span');
    wave.className = 'price-wave';
    surface.append(wave);
    row.append(surface);
    return { row, cells, name };
}
export function updateSymbolRow(row, symbol, active, state, attention) {
    row.classList.toggle('active', active);
    row.querySelector('.ticker').setAttribute('aria-pressed', String(active));
    stateAppearance(row, state);
    attentionAppearance(row, symbol, attention);
    const adr = row.querySelector('[data-field="state-adr"]');
    if (adr) {
        adr.textContent = adrText(state);
        adr.title = adrTitle(state);
    }
    for (const [field, value] of [['cum-vol', state?.cum_vol], ['local-vol', state?.local_vol]]) {
        const cell = row.querySelector(`[data-field="${field}"]`);
        if (cell)
            volumeBadge(cell, value);
    }
}
export function adjacentSymbol(symbols, selected, direction) {
    const ordered = Array.from(symbols);
    const index = Math.max(0, Math.min(ordered.length - 1, ordered.indexOf(selected) + direction));
    return ordered[index];
}
export function revealSymbolRow(row, scroll = true) {
    row?.focus({ preventScroll: true });
    if (scroll)
        row?.scrollIntoView({ block: 'nearest', inline: 'nearest' });
}
