import { attentionAppearance, type Attention } from './attention.js';
import { adrText, adrTitle, stateAppearance, volumeBadge, type SymbolState } from './intraday-state.js';

export type ListColumn<Field extends string = string> = { field: Field; label: string; width: string };

export function extendedPercentText(value: number | null) {
    if (value == null) return '';
    const magnitude = Math.abs(value).toFixed(2);
    return magnitude === '0.00' ? '' : `${value < 0 ? '-' : '+'}${magnitude}%`;
}

export function setListColumns(host: HTMLElement, columns: readonly ListColumn[], priceEnd: string) {
    host.style.setProperty('--list-columns', columns.map(({ field, width }) => `[col-${field}] ${width}`).join(' '));
    host.style.setProperty('--price-end', `col-${priceEnd}`);
}

export function listMinimumWidth(grid: HTMLElement, content = grid) {
    const viewport = content.parentElement!;
    const { marginLeft, marginRight } = getComputedStyle(content);
    grid.style.width = 'min-content';
    const width = grid.getBoundingClientRect().width;
    grid.style.removeProperty('width');
    return Math.ceil(width + parseFloat(marginLeft) + parseFloat(marginRight) + viewport.offsetWidth - viewport.clientWidth);
}

function listCell(field: string) {
    const cell = document.createElement('div');
    cell.dataset.field = field;
    cell.style.gridColumn = `col-${field}`;
    return cell;
}

export function listCells<Field extends string>(row: HTMLElement, columns: readonly ListColumn<Field>[], semantic = false) {
    if (semantic) row.setAttribute('role', 'row');
    const cells = {} as Record<Field, HTMLElement>;
    for (const { field } of columns) {
        const cell = listCell(field);
        if (semantic) cell.setAttribute('role', 'cell');
        row.append(cell);
        cells[field] = cell;
    }
    return cells;
}

export function listHeader<Field extends string>(row: HTMLElement, columns: readonly ListColumn<Field>[],
        customize: (cell: HTMLElement, column: ListColumn<Field>) => void) {
    row.replaceChildren(...columns.map(column => {
        const cell = listCell(column.field);
        cell.textContent = column.label;
        customize(cell, column);
        return cell;
    }));
}

export function symbolRow<Field extends string>(ticker: string, columns: readonly ListColumn<Field>[], priceEnd: Field, semantic = false) {
    const row = document.createElement('div');
    row.className = 'list-grid-row symbol-row';
    row.tabIndex = -1;
    const priceEndIndex = columns.findIndex(column => column.field === priceEnd);
    const cells = listCells(row, columns, semantic) as Record<Field | 'symbol', HTMLElement>;
    for (const { field } of columns.slice(0, priceEndIndex)) cells[field].classList.add('price-cell');

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

export function updateSymbolRow(row: HTMLElement, symbol: string, active: boolean, state: SymbolState | undefined, attention: Attention) {
    row.classList.toggle('active', active);
    row.querySelector('.ticker')!.setAttribute('aria-pressed', String(active));
    stateAppearance(row, state);
    attentionAppearance(row, symbol, attention);
    const adr = row.querySelector<HTMLElement>('[data-field="state-adr"]');
    if (adr) {
        adr.textContent = adrText(state);
        adr.title = adrTitle(state);
    }
    for (const [field, value] of [['cum-vol', state?.cum_vol], ['local-vol', state?.local_vol]] as const) {
        const cell = row.querySelector<HTMLElement>(`[data-field="${field}"]`);
        if (cell) volumeBadge(cell, value);
    }
}

export function adjacentSymbol(symbols: Iterable<string>, selected: string, direction: number): string | undefined {
    const ordered = Array.from(symbols);
    const index = Math.max(0, Math.min(ordered.length - 1, ordered.indexOf(selected) + direction));
    return ordered[index];
}

export function revealSymbolRow(row?: HTMLElement, scroll = true) {
    row?.focus({ preventScroll: true });
    if (scroll) row?.scrollIntoView({ block: 'nearest', inline: 'nearest' });
}
