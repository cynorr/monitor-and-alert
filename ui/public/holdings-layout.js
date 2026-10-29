// DOM geometry shared by both native account views; never measures allocated scrollWidth.
export class HoldingsLayout {
    table;
    end;
    changed;
    signature = '';
    minimum = 0;
    constructor(table, end, changed) {
        this.table = table;
        this.end = end;
        this.changed = changed;
        new ResizeObserver(() => this.priceWidth()).observe(table);
    }
    reset() { this.minimum = 0; this.signature = ''; }
    invalidate() { this.signature = ''; }
    measure() {
        const table = this.table;
        if (!table.getClientRects().length)
            return;
        const signature = JSON.stringify([table.className, Array.from(table.rows, row => Array.from(row.cells, cell => getComputedStyle(cell).display === 'none' ? null : cell.textContent?.length))]);
        if (signature !== this.signature) {
            this.signature = signature;
            const copy = table.cloneNode(true);
            copy.removeAttribute('id');
            copy.querySelectorAll('[id]').forEach(node => node.removeAttribute('id'));
            copy.querySelectorAll('.price-surface').forEach(node => node.remove());
            copy.classList.add('holdings-measure');
            copy.setAttribute('aria-hidden', 'true');
            document.body.append(copy);
            const width = Math.ceil(copy.getBoundingClientRect().width);
            copy.remove();
            const scroll = table.closest('.holdings-scroll'), style = getComputedStyle(scroll);
            this.minimum = Math.max(this.minimum, width + parseFloat(style.paddingLeft) + parseFloat(style.paddingRight) + scroll.offsetWidth - scroll.clientWidth);
        }
        this.changed(this.minimum);
        this.priceWidth();
    }
    priceWidth() {
        const table = this.table, end = table.tHead?.rows[0].cells[this.end()], first = table.tBodies[0]?.rows[0]?.cells[0];
        if (!end || !first || !table.getClientRects().length)
            return;
        const origin = first.getBoundingClientRect().left + parseFloat(getComputedStyle(first).borderLeftWidth);
        table.style.setProperty('--holding-price-width', `${Math.max(0, end.getBoundingClientRect().right - origin)}px`);
    }
}
