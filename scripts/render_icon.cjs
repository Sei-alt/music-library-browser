// Development-only renderer: npm install sharp, then node scripts/render_icon.cjs
const fs = require('node:fs');
const path = require('node:path');
const sharp = require('sharp');
const assets = path.join(__dirname, '..', 'assets');
(async () => {
  await sharp(path.join(assets, 'music-library.svg')).resize(1024).png().toFile(path.join(assets, 'music-library.png'));
  // ICO embeds lossless PNG frames. Windows chooses a frame for each DPI/size.
  const sizes = [16, 20, 24, 32, 40, 48, 64, 96, 128, 256];
  const frames = await Promise.all(sizes.map(size => sharp(path.join(assets, 'music-library.svg')).resize(size).png().toBuffer()));
  const header = Buffer.alloc(6 + sizes.length * 16);
  header.writeUInt16LE(1, 2); header.writeUInt16LE(sizes.length, 4);
  let offset = header.length;
  sizes.forEach((size, index) => {
    const at = 6 + index * 16;
    header[at] = header[at + 1] = size === 256 ? 0 : size;
    header.writeUInt16LE(1, at + 4); header.writeUInt16LE(32, at + 6);
    header.writeUInt32LE(frames[index].length, at + 8); header.writeUInt32LE(offset, at + 12);
    offset += frames[index].length;
  });
  fs.writeFileSync(path.join(assets, 'music-library.ico'), Buffer.concat([header, ...frames]));
})();
