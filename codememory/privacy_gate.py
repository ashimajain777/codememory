import re
import os

PATTERNS = {
    'AWS_KEY': r'(?i)AKIA[0-9A-Z]{16}',
    'GITHUB_TOKEN': r'(?i)gh[pousr]_[A-Za-z0-9_]{36,255}',
    'SLACK_TOKEN': r'(?i)xox[baprs]-[0-9]{10,13}-[a-zA-Z0-9]{24}',
    'STRIPE_KEY': r'(?i)(sk_live|rk_live)_[a-zA-Z0-9]{24,99}',
    'PRIVATE_KEY': r'-----BEGIN\s+.*PRIVATE\s+KEY-----',
    'JWT': r'eyJ[a-zA-Z0-9_-]{5,}\.eyJ[a-zA-Z0-9_-]{5,}\.[a-zA-Z0-9_-]{5,}',
    'PASSWORD_IN_URL': r'(?i)(?:[a-z]+://)?(?:[a-zA-Z0-9_.-]+):([^@\s/]+)@',
    'EMAIL': r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+',
    'PRIVATE_IP': r'(^|\s)(10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|172\.(1[6-9]|2[0-9]|3[0-1])\.\d{1,3}\.\d{1,3})(\s|$)',
    'INTERNAL_HOSTNAME': r'(?i)[a-zA-Z0-9.-]+\.(internal|corp|local)\b',
    'PHONE_NUMBER': r'\+?[1-9]\d{1,14}(?:[\s-]?\d{1,14})*'
}

def mask_value(val, ptype):
    if ptype in ['EMAIL', 'INTERNAL_HOSTNAME', 'PRIVATE_IP', 'PHONE_NUMBER']:
        return f"[REDACTED:{ptype}]"
    if len(val) <= 6:
        return "***"
    return f"{val[:3]}...{val[-3:]}"

class PrivacyGate:
    def __init__(self, mode='redact', local_only=False):
        self.mode = mode
        self.local_only = local_only
        self.findings = []
        
    def check_endpoint(self, url):
        if self.local_only:
            if not ('localhost' in url or '127.0.0.1' in url):
                raise ValueError(f"Local-only mode refused non-local endpoint: {url}")
                
    def process_text(self, text, filepath=""):
        lines = text.split('\n')
        redacted_lines = []
        has_blocker = False
        
        for i, line in enumerate(lines):
            redacted_line = line
            for ptype, pattern in PATTERNS.items():
                for match in re.finditer(pattern, redacted_line):
                    val = match.group(0)
                    if ptype == 'PASSWORD_IN_URL':
                        val = match.group(1) # The actual password part
                    
                    self.findings.append({
                        'type': ptype,
                        'file': filepath,
                        'line': i + 1,
                        'masked': mask_value(val, ptype)
                    })
                    
                    if self.mode == 'block':
                        has_blocker = True
                    elif self.mode == 'redact':
                        if ptype == 'PASSWORD_IN_URL':
                            redacted_line = redacted_line.replace(val, f"[REDACTED:{ptype}]")
                        else:
                            redacted_line = redacted_line.replace(val, f"[REDACTED:{ptype}]")
            redacted_lines.append(redacted_line)
            
        if self.mode == 'block' and has_blocker:
            raise ValueError(f"Blocked due to privacy findings in {filepath}")
            
        return "\n".join(redacted_lines)

    def generate_report(self):
        report = {"counts": {}, "details": []}
        for f in self.findings:
            t = f['type']
            report['counts'][t] = report['counts'].get(t, 0) + 1
            report['details'].append(f"{f['file']}:{f['line']} ({t}) {f['masked']}")
        return report
