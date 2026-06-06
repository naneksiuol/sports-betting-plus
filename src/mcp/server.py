import pandas as pd
from pathlib import Path
from mcp.server.fastmcp import FastMCP

# Create MCP server
mcp = FastMCP("Sports Betting Plus - MLB Hits")

DATA_PATH = Path(__file__).parent.parent.parent / "data" / "hits_board-1.csv"


def load_hits_data():
    if not DATA_PATH.exists():
        raise FileNotFoundError(f"Data file not found at {DATA_PATH}")
    df = pd.read_csv(DATA_PATH)
    df['last5'] = pd.to_numeric(df['last5'], errors='coerce').fillna(0.0)
    df['edge'] = df['fair_est'] - df['book_implied']
    return df


@mcp.tool()
def get_mlb_value_picks(
    min_edge: float = 0.03,
    min_last5: float = 0.15,
    limit: int = 15
) -> str:
    """
    Get MLB 1+ hits value bets from the current board.
    
    Args:
        min_edge: Minimum probability edge required (default 0.03 = 3%)
        min_last5: Minimum hit rate in last 5 games (default 0.15)
        limit: Maximum number of results to return
    
    Returns:
        Formatted string with top value picks including player, team, edge, and probabilities.
    """
    df = load_hits_data()
    
    filtered = df[
        (df['edge'] >= min_edge) & 
        (df['last5'] >= min_last5)
    ].sort_values('edge', ascending=False).head(limit)
    
    if filtered.empty:
        return "No value picks found with the current filters."
    
    result = "**Top MLB 1+ Hits Value Picks**\n\n"
    for _, row in filtered.iterrows():
        result += f"- **{row['player']}** ({row['team']})\n"
        result += f"  Edge: +{row['edge']:.2%} | Last5: {row['last5']:.1%}\n"
        result += f"  Fair: {row['fair_est']:.1%} vs Book: {row['book_implied']:.1%}\n\n"
    return result


@mcp.tool()
def get_top_mlb_edges(limit: int = 10) -> str:
    """
    Get the highest edge MLB 1+ hits plays currently available.
    
    Args:
        limit: Number of top plays to return
    
    Returns:
        Top plays by edge with key details.
    """
    df = load_hits_data()
    top = df.sort_values('edge', ascending=False).head(limit)
    
    result = "**Highest Edge MLB Hits Plays**\n\n"
    for _, row in top.iterrows():
        result += f"- **{row['player']}** ({row['team']}) — Edge: +{row['edge']:.2%}\n"
    return result


if __name__ == "__main__":
    mcp.run()
