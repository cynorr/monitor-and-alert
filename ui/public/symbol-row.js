// One price surface for both grid watchlist rows and table holdings rows.
export function symbolRow(row, host = row) {
    row.classList.add('instrument-row');
    const surface = document.createElement('span');
    surface.className = 'price-surface';
    surface.setAttribute('aria-hidden', 'true');
    const wave = document.createElement('span');
    wave.className = 'price-wave';
    surface.append(wave);
    host.append(surface);
}
