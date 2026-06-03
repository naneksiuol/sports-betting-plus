import pandas as pd


def find_value_bets(csv_path="data/hits_board-1.csv", min_edge=0.03, top_n=20):
    """
    Scan the hits board for positive expected value ( +EV ) bets on 1+ hits.
    
    Parameters
    ----------
    csv_path : str
        Path to the hits board CSV.
    min_edge : float
        Minimum probability edge (fair_est - book_implied) to consider value.
    top_n : int
        Number of top value bets to return.
    
    Returns
    -------
    pd.DataFrame
        Top value bets sorted by edge descending.
    """
    df = pd.read_csv(csv_path)
    
    # Calculate edge
    df['edge'] = df['fair_est'] - df['book_implied']
    
    # Filter for value bets
    value_df = df[df['edge'] >= min_edge].copy()
    
    if value_df.empty:
        print("No value bets found with the current edge threshold.")
        return pd.DataFrame()
    
    # Sort by edge
    value_df = value_df.sort_values('edge', ascending=False).head(top_n)
    
    # Select and format relevant columns
    cols = ['player', 'team', 'last5', 'odds_1plus', 'book_implied', 'fair_est', 'edge']
    result = value_df[cols].reset_index(drop=True)
    
    print(f"\n=== TOP {len(result)} VALUE BETS (edge >= {min_edge:.0%}) ===\n")
    print(result.to_string(index=False))
    
    return result


if __name__ == "__main__":
    # Example usage
    find_value_bets(min_edge=0.04, top_n=15)
