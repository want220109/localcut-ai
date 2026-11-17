import {build} from 'esbuild';
import fs from 'node:fs/promises';
await fs.mkdir('build/electron',{recursive:true});
await build({entryPoints:['desktop/electron/main.cjs'],outfile:'build/electron/main.cjs',bundle:true,platform:'node',format:'cjs',external:['electron','electron-updater']});
await fs.copyFile('desktop/electron/preload.cjs','build/electron/preload.cjs');
