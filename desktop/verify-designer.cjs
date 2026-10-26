// Compatibility test entry: verify the released System Template and DIY gate.
process.argv.push('--test-only');
require('../scripts/record-system-demo.cjs');
