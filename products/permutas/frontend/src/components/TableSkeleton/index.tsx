import { memo } from 'react'
import styled, { keyframes } from 'styled-components'
import { color, spacing } from '../../styles'

const shimmer = keyframes`
  0% {
    background-position: -200px 0;
  }
  100% {
    background-position: calc(200px + 100%) 0;
  }
`

const SkeletonRow = styled.tr``

const SkeletonCell = styled.td`
  padding: ${spacing.md};
  border-bottom: 1px solid ${color.border};
`

const SkeletonBar = styled.div<{ $width?: string }>`
  height: 16px;
  width: ${({ $width }) => $width || '100%'};
  background: linear-gradient(
    90deg,
    ${color.border} 0%,
    ${color.backgroundDark} 50%,
    ${color.border} 100%
  );
  background-size: 200px 100%;
  animation: ${shimmer} 1.2s ease-in-out infinite;
  border-radius: 2px;
`

const SkeletonAction = styled.div`
  display: inline-flex;
  gap: ${spacing.sm};
`

const SkeletonActionButton = styled.div`
  width: 24px;
  height: 24px;
  background: linear-gradient(
    90deg,
    ${color.border} 0%,
    ${color.backgroundDark} 50%,
    ${color.border} 100%
  );
  background-size: 200px 100%;
  animation: ${shimmer} 1.2s ease-in-out infinite;
  border-radius: 2px;
`

const ActionsSkeletonCell = styled.td`
  padding: ${spacing.md};
  border-bottom: 1px solid ${color.border};
  text-align: right;
`

type TableSkeletonProps = {
  rows?: number
  columns: number
  hasActions?: boolean
}

const columnWidths = ['60%', '80%', '70%', '50%', '90%', '65%', '75%', '55%']

const TableSkeleton = memo(({ rows = 5, columns, hasActions = false }: TableSkeletonProps) => {
  return (
    <>
      {Array.from({ length: rows }).map((_, rowIndex) => (
        <SkeletonRow key={rowIndex}>
          {Array.from({ length: columns }).map((_, colIndex) => (
            <SkeletonCell key={colIndex}>
              <SkeletonBar $width={columnWidths[(rowIndex + colIndex) % columnWidths.length]} />
            </SkeletonCell>
          ))}
          {hasActions && (
            <ActionsSkeletonCell>
              <SkeletonAction>
                <SkeletonActionButton />
                <SkeletonActionButton />
              </SkeletonAction>
            </ActionsSkeletonCell>
          )}
        </SkeletonRow>
      ))}
    </>
  )
})

TableSkeleton.displayName = 'TableSkeleton'

export default TableSkeleton
