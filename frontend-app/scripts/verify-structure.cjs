/* eslint-env node */
const fs = require('fs');
const path = require('path');

console.log('Verifying frontend directory structure...');

// Define required directories based on the project plan [cite: 114-116]
const requiredDirs = [
  'src/components',
  'src/hooks',
  'src/services',
];

let allDirsExist = true;

requiredDirs.forEach(dir => {
  // Construct the full path relative to the project's root directory
  const fullPath = path.join(__dirname, '..', dir);
  if (!fs.existsSync(fullPath)) {
    console.error(`❌ FAILED: Required directory is missing: ${dir}`);
    allDirsExist = false;
  } else {
    console.log(`✅ OK: Found directory: ${dir}`);
  }
});

if (!allDirsExist) {
  console.error('\nStructural check failed. Please create the missing directories to ensure consistency.');
  process.exit(1); // Exit with a failure code
}

console.log('\n✅ Frontend structure verification passed!');
process.exit(0); // Exit with a success code