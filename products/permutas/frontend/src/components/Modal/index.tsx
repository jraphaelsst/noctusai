import { useEffect } from 'react'
import { createPortal } from 'react-dom'
import styled, { keyframes } from 'styled-components'
import { color, spacing, breakpoints } from '../../styles'

const fadeIn = keyframes`
  from {
    opacity: 0;
  }
  to {
    opacity: 1;
  }
`

const slideUp = keyframes`
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
`

const Overlay = styled.div`
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(45, 52, 54, 0.7);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  animation: ${fadeIn} 0.2s ease;
  padding: ${spacing.lg};
`

const ModalContainer = styled.div`
  background: ${color.cardBg};
  box-shadow: 0 20px 60px rgba(45, 52, 54, 0.25);
  max-width: 600px;
  width: 100%;
  max-height: 90vh;
  overflow-y: auto;
  animation: ${slideUp} 0.2s ease;

  @media (max-width: ${breakpoints.tablet}) {
    max-width: 100%;
  }
`

const ModalHeader = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: ${spacing.lg} ${spacing.xl};
  border-bottom: 1px solid ${color.border};
`

const ModalTitle = styled.h2`
  font-size: 1.125rem;
  font-weight: 600;
  color: ${color.text};
  margin: 0;
`

const CloseButton = styled.button`
  background: none;
  border: none;
  font-size: 1.25rem;
  color: ${color.textMuted};
  cursor: pointer;
  padding: ${spacing.xs};
  line-height: 1;
  transition: color 0.2s ease;

  &:hover {
    color: ${color.text};
  }
`

const ModalBody = styled.div`
  padding: ${spacing.xl};
`

const ModalFooter = styled.div`
  display: flex;
  justify-content: flex-end;
  gap: ${spacing.md};
  padding: ${spacing.lg} ${spacing.xl};
  border-top: 1px solid ${color.border};
`

type Props = {
  isOpen: boolean
  onClose: () => void
  title: string
  children: React.ReactNode
  footer?: React.ReactNode
}

const Modal = ({ isOpen, onClose, title, children, footer }: Props) => {
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose()
      }
    }

    if (isOpen) {
      document.addEventListener('keydown', handleEscape)
      document.body.style.overflow = 'hidden'
    }

    return () => {
      document.removeEventListener('keydown', handleEscape)
      document.body.style.overflow = 'unset'
    }
  }, [isOpen, onClose])

  if (!isOpen) return null

  const handleOverlayClick = (e: React.MouseEvent) => {
    if (e.target === e.currentTarget) {
      onClose()
    }
  }

  const modalContent = (
    <Overlay onClick={handleOverlayClick}>
      <ModalContainer onClick={(e) => e.stopPropagation()}>
        <ModalHeader>
          <ModalTitle>{title}</ModalTitle>
          <CloseButton type="button" onClick={onClose}>&times;</CloseButton>
        </ModalHeader>
        <ModalBody>{children}</ModalBody>
        {footer && <ModalFooter>{footer}</ModalFooter>}
      </ModalContainer>
    </Overlay>
  )

  return createPortal(modalContent, document.body)
}

export default Modal
