import React, { useState, useEffect } from 'react';
import { AlertCircle, CheckCircle, Clock, Brain, Zap, BookOpen, Heart, Calendar, TrendingUp, Briefcase } from 'lucide-react';
import styles from './AIPipeline.module.css';

/**
 * AIPipeline Component
 * Shows AI reasoning process in real-time like Perplexity
 *
 * Displays:
 * 1. Intent parsing (what student is asking)
 * 2. Agent selection (which agents to invoke)
 * 3. Context loading (ERP data, learning DNA, sentiment)
 * 4. Agent reasoning (what each agent is computing)
 * 5. Response synthesis (combining insights)
 * 6. Confidence score (how confident is the response?)
 */

const AGENT_ICONS = {
  academic: <BookOpen size={16} />,
  prediction: <TrendingUp size={16} />,
  emotional: <Heart size={16} />,
  learning: <Brain size={16} />,
  schedule: <Calendar size={16} />,
  career: <Briefcase size={16} />,
};

const AGENT_COLORS = {
  academic: '#3b82f6',
  prediction: '#f59e0b',
  emotional: '#ec4899',
  learning: '#10b981',
  schedule: '#8b5cf6',
  career: '#06b6d4',
};

export default function AIPipeline({
  pipelineData,
  isLoading,
  expanded = false,
  onToggle
}) {
  const [visibleStages, setVisibleStages] = useState([]);

  // Animate stages appearing
  useEffect(() => {
    if (!pipelineData) return;

    const stages = pipelineData.stages || [];
    const timings = stages.map((_, idx) => {
      return setTimeout(() => {
        setVisibleStages(prev => [...prev, idx]);
      }, idx * 200);
    });

    return () => timings.forEach(t => clearTimeout(t));
  }, [pipelineData]);

  if (!pipelineData && !isLoading) return null;

  return (
    <div className={`${styles.pipeline} ${expanded ? styles.expanded : ''}`}>
      {/* Header */}
      <div className={styles.header} onClick={onToggle}>
        <div className={styles.title}>
          <Brain size={18} />
          <span>AI Thinking Process</span>
        </div>
        <span className={styles.toggle}>{expanded ? '−' : '+'}</span>
      </div>

      {/* Main Pipeline */}
      {expanded && (
        <div className={styles.content}>
          {/* Intent Parsing Stage */}
          {pipelineData?.intent && (
            <div className={`${styles.stage} ${visibleStages.includes(0) ? styles.visible : ''}`}>
              <div className={styles.stageHeader}>
                <span className={styles.icon}>📝</span>
                <span className={styles.label}>Understanding Your Question</span>
                {pipelineData.intent.confidence && (
                  <span className={styles.confidence}>
                    {Math.round(pipelineData.intent.confidence * 100)}% confident
                  </span>
                )}
              </div>
              <div className={styles.details}>
                <p><strong>What you asked:</strong> "{pipelineData.intent.user_message}"</p>
                <p><strong>Intent detected:</strong> <code>{pipelineData.intent.intent}</code></p>
                {pipelineData.intent.reasoning && (
                  <p><strong>Why:</strong> {pipelineData.intent.reasoning}</p>
                )}
              </div>
            </div>
          )}

          {/* Agent Selection Stage */}
          {pipelineData?.agent_selection && (
            <div className={`${styles.stage} ${visibleStages.includes(1) ? styles.visible : ''}`}>
              <div className={styles.stageHeader}>
                <span className={styles.icon}>🎯</span>
                <span className={styles.label}>Selecting Best Agents</span>
              </div>
              <div className={styles.details}>
                <p><strong>Primary Agent:</strong></p>
                <div className={styles.agentBadge} style={{ borderLeft: `4px solid ${AGENT_COLORS[pipelineData.agent_selection.primary]}` }}>
                  {AGENT_ICONS[pipelineData.agent_selection.primary]}
                  <span>{pipelineData.agent_selection.primary}</span>
                </div>

                {pipelineData.agent_selection.supporting?.length > 0 && (
                  <>
                    <p><strong>Supporting Agents:</strong></p>
                    <div className={styles.supportingAgents}>
                      {pipelineData.agent_selection.supporting.map(agent => (
                        <div
                          key={agent}
                          className={styles.agentBadge}
                          style={{ borderLeft: `4px solid ${AGENT_COLORS[agent]}` }}
                        >
                          {AGENT_ICONS[agent]}
                          <span>{agent}</span>
                        </div>
                      ))}
                    </div>
                  </>
                )}

                {pipelineData.agent_selection.reasoning && (
                  <p><em>{pipelineData.agent_selection.reasoning}</em></p>
                )}
              </div>
            </div>
          )}

          {/* Context Loading Stage */}
          {pipelineData?.context && (
            <div className={`${styles.stage} ${visibleStages.includes(2) ? styles.visible : ''}`}>
              <div className={styles.stageHeader}>
                <span className={styles.icon}>📚</span>
                <span className={styles.label}>Gathering Your Context</span>
              </div>
              <div className={styles.details}>
                <div className={styles.contextGrid}>
                  {pipelineData.context.profile && (
                    <div className={styles.contextItem}>
                      <span className={styles.contextLabel}>Profile</span>
                      <div className={styles.contextValue}>
                        CGPA: {pipelineData.context.profile.cgpa} |
                        Year: {pipelineData.context.profile.year}
                      </div>
                    </div>
                  )}
                  {pipelineData.context.sentiment && (
                    <div className={styles.contextItem}>
                      <span className={styles.contextLabel}>Emotional State</span>
                      <div className={styles.contextValue}>
                        {pipelineData.context.sentiment > 0 ? '😊 Positive' : pipelineData.context.sentiment < 0 ? '😟 Struggling' : '😐 Neutral'}
                        ({pipelineData.context.sentiment.toFixed(2)})
                      </div>
                    </div>
                  )}
                  {pipelineData.context.bloom && (
                    <div className={styles.contextItem}>
                      <span className={styles.contextLabel}>Knowledge Level</span>
                      <div className={styles.contextValue}>
                        Bloom L{pipelineData.context.bloom}/6
                      </div>
                    </div>
                  )}
                  {pipelineData.context.learning_style && (
                    <div className={styles.contextItem}>
                      <span className={styles.contextLabel}>Learning Style</span>
                      <div className={styles.contextValue}>
                        {pipelineData.context.learning_style}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Agent Reasoning Stage */}
          {pipelineData?.agent_outputs && (
            <div className={`${styles.stage} ${visibleStages.includes(3) ? styles.visible : ''}`}>
              <div className={styles.stageHeader}>
                <span className={styles.icon}>🧠</span>
                <span className={styles.label}>AI Agents Computing</span>
              </div>
              <div className={styles.agentOutputs}>
                {Object.entries(pipelineData.agent_outputs).map(([agent, output]) => (
                  <div
                    key={agent}
                    className={styles.agentOutput}
                    style={{ borderLeft: `3px solid ${AGENT_COLORS[agent]}` }}
                  >
                    <div className={styles.agentName}>
                      {AGENT_ICONS[agent]} <strong>{agent}</strong>
                    </div>
                    <div className={styles.agentThinking}>
                      {output.reasoning && (
                        <p><strong>Reasoning:</strong> {output.reasoning}</p>
                      )}
                      {output.key_insight && (
                        <p><strong>Key Insight:</strong> {output.key_insight}</p>
                      )}
                      {output.score && (
                        <p><strong>Confidence:</strong> {Math.round(output.score * 100)}%</p>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Response Synthesis Stage */}
          {pipelineData?.synthesis && (
            <div className={`${styles.stage} ${visibleStages.includes(4) ? styles.visible : ''}`}>
              <div className={styles.stageHeader}>
                <span className={styles.icon}>✨</span>
                <span className={styles.label}>Synthesizing Response</span>
              </div>
              <div className={styles.details}>
                {pipelineData.synthesis.response_mode && (
                  <p><strong>Mode:</strong> <code>{pipelineData.synthesis.response_mode}</code></p>
                )}
                {pipelineData.synthesis.tone && (
                  <p><strong>Tone:</strong> {pipelineData.synthesis.tone}</p>
                )}
                {pipelineData.synthesis.personalization && (
                  <p><strong>Personalization:</strong> {pipelineData.synthesis.personalization.join(', ')}</p>
                )}
                {pipelineData.synthesis.ui_widgets && pipelineData.synthesis.ui_widgets.length > 0 && (
                  <p><strong>UI Components:</strong> {pipelineData.synthesis.ui_widgets.join(', ')}</p>
                )}
              </div>
            </div>
          )}

          {/* Overall Confidence */}
          {pipelineData?.overall_confidence && (
            <div className={styles.confidenceBar}>
              <span>Overall Response Confidence</span>
              <div className={styles.bar}>
                <div
                  className={styles.fill}
                  style={{
                    width: `${pipelineData.overall_confidence * 100}%`,
                    backgroundColor: pipelineData.overall_confidence > 0.7 ? '#10b981' : '#f59e0b'
                  }}
                />
              </div>
              <span>{Math.round(pipelineData.overall_confidence * 100)}%</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
