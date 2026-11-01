import React from 'react';
import * as Popover from '@radix-ui/react-popover';
import { ArrowUpRight, X } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import usePanelHost from '../hooks/usePanelHost';

function Citation({ source, number, caseId }) {
  const host = usePanelHost(true),
    navigate = useNavigate();
  const target = source.case_id || caseId;
  return (
    <Popover.Root>
      <Popover.Trigger
        className="citation-trigger"
        aria-label={`Source ${number}: ${source.label}`}
      >
        [{number}]
      </Popover.Trigger>
      <Popover.Portal container={host || undefined}>
        <Popover.Content
          className="citation-popover"
          aria-label={`Source ${number}: ${source.label}`}
          data-helm-popover
          sideOffset={8}
          collisionPadding={16}
        >
          <div className="section-header">
            <strong>{source.label}</strong>
            <Popover.Close className="icon-button" aria-label="Close source">
              <X size={15} />
            </Popover.Close>
          </div>
          {source.excerpt && <p>{source.excerpt}</p>}
          <small>
            {source.method?.replaceAll('_', ' ')}
            {source.pages ? ` · ${source.pages} pages` : ''}
          </small>
          <code>{source.record || source.sha256}</code>
          {target && (
            <Popover.Close asChild>
              <button
                className="text-button"
                onClick={() =>
                  navigate(
                    `/case/${encodeURIComponent(target)}?view=${encodeURIComponent(source.view || 'audit')}`,
                  )
                }
              >
                Open saved source <ArrowUpRight size={14} />
              </button>
            </Popover.Close>
          )}
          <Popover.Arrow className="citation-arrow" />
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}

export default function AssistantCitations({ text, sources = [], caseId }) {
  return (
    <div className="assistant-answer">
      {text.split(/(\[\d+\])/).map((part, index) => {
        const number = /^\[\d+\]$/.test(part) ? Number(part.slice(1, -1)) : 0;
        return number && sources[number - 1] ? (
          <Citation key={index} source={sources[number - 1]} number={number} caseId={caseId} />
        ) : (
          part
        );
      })}
    </div>
  );
}
